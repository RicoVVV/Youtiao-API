"""渠道健康探测用例：最小请求探测、连续失败自动停用与恢复后自动启用。"""

import asyncio
import logging
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.bootstrap.container import get_channel_provider_factory, get_provider_template_registry
from app.core.config import get_settings
from app.modules.channels.application.model_mapping import apply_upstream_model_name
from app.modules.channels.crud.channels import ChannelCrud
from app.modules.channels.runtime.channel_runtime import ProbeRuntimeResult, get_channel_runtime
from app.modules.channels.runtime.routing_snapshot import publish_routing_snapshot_invalidation
from app.modules.providers.contracts import GenerationProvider, ProviderError

logger = logging.getLogger(__name__)

_PROBE_MESSAGE = "hi"
_PROBE_MAX_TOKENS = 16


@dataclass(frozen=True, slots=True)
class _ProbeTarget:
    """一个渠道的最小探测目标；``provider`` 为空表示该渠道没有可探测的文本模型。"""

    channel_id: UUID
    channel_name: str
    auto_disabled: bool
    route_ids: list[UUID]
    provider: GenerationProvider | None
    request_body: dict[str, Any] | None


class ChannelHealthProbeApplicationService:
    """对启用渠道与自动停用渠道执行最小请求探测，并驱动渠道生命周期。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._settings = get_settings()

    async def probe_all(self) -> dict[str, int]:
        """执行一轮探测，返回本轮统计。单渠道异常不影响其他渠道。"""

        targets = await self._load_targets()
        semaphore = asyncio.Semaphore(self._settings.routing_probe_concurrency)
        results = await asyncio.gather(
            *(self._probe_one(target, semaphore) for target in targets), return_exceptions=True
        )
        counters = {"probed": 0, "succeeded": 0, "failed": 0, "disabled": 0, "enabled": 0, "skipped": 0}
        for target, result in zip(targets, results, strict=True):
            if isinstance(result, BaseException):
                logger.warning("渠道健康探测异常 channel_id=%s", target.channel_id, exc_info=result)
                counters["failed"] += 1
                continue
            counters[result] += 1
        logger.info("渠道健康探测完成 %s", counters)
        return counters

    async def _probe_one(self, target: _ProbeTarget, semaphore: asyncio.Semaphore) -> str:
        if target.provider is None or target.request_body is None:
            return "skipped"
        chat = getattr(target.provider, "chat", None)
        if not callable(chat):
            return "skipped"
        async with semaphore:
            if await asyncio.to_thread(self._should_skip_disabled, target):
                return "skipped"
            started_at_counter = perf_counter()
            succeeded = False
            try:
                await chat(target.request_body, timeout=self._settings.routing_probe_timeout_seconds)
                succeeded = True
            except ProviderError as exc:
                logger.info("渠道健康探测失败 channel_id=%s code=%s message=%s", target.channel_id, exc.code, exc)
            except Exception:
                logger.warning("渠道健康探测调用异常 channel_id=%s", target.channel_id, exc_info=True)
            latency_ms = max(0, round((perf_counter() - started_at_counter) * 1000))
        runtime_result = await asyncio.to_thread(
            self._record_probe,
            target.channel_id,
            succeeded,
            latency_ms,
        )
        applied = await self._apply_lifecycle(target, succeeded=succeeded, runtime=runtime_result)
        if applied == "disabled" or applied == "enabled":
            return applied
        return "succeeded" if succeeded else "failed"

    def _should_skip_disabled(self, target: _ProbeTarget) -> bool:
        """已自动停用的渠道按更低频率探测，避免每轮都消耗上游额度。"""

        if not target.auto_disabled:
            return False
        try:
            state = self._runtime().read_channel_state(target.channel_id)
            last_probe_at = int(state.get("last_probe_at") or 0)
        except Exception:
            return False
        elapsed_ms = int(datetime.now(UTC).timestamp() * 1000) - last_probe_at
        return 0 <= elapsed_ms < self._settings.routing_probe_disabled_interval_seconds * 1000

    def _record_probe(self, channel_id: UUID, succeeded: bool, latency_ms: int) -> ProbeRuntimeResult:
        try:
            return self._runtime().record_probe_outcome(channel_id=channel_id, success=succeeded, latency_ms=latency_ms)
        except Exception:
            logger.warning("渠道探测状态写入失败 channel_id=%s", channel_id, exc_info=True)
            return ProbeRuntimeResult(state="closed", probe_fails=0, probe_successes=0)

    async def _apply_lifecycle(
        self, target: _ProbeTarget, *, succeeded: bool, runtime: ProbeRuntimeResult
    ) -> str | None:
        if (
            not succeeded
            and not target.auto_disabled
            and runtime.probe_fails >= self._settings.routing_probe_failure_threshold
        ):
            disabled = await self._set_auto_disabled(target.channel_id, disabled=True)
            return "disabled" if disabled else None
        if (
            succeeded
            and target.auto_disabled
            and runtime.probe_successes >= self._settings.routing_probe_recovery_threshold
        ):
            enabled = await self._set_auto_disabled(target.channel_id, disabled=False)
            return "enabled" if enabled else None
        return None

    async def _set_auto_disabled(self, channel_id: UUID, *, disabled: bool) -> bool:
        async with self._session_factory() as session:
            route_ids = await session.run_sync(_apply_auto_state, channel_id, disabled)
        if route_ids is None:
            return False
        try:
            if not disabled:
                await asyncio.to_thread(self._runtime().reset_channel, channel_id=channel_id, route_ids=route_ids)
        except Exception:
            logger.warning("渠道运行时状态重置失败 channel_id=%s", channel_id, exc_info=True)
        publish_routing_snapshot_invalidation()
        logger.warning("渠道已%s channel_id=%s", "自动停用" if disabled else "自动恢复启用", channel_id)
        return True

    async def _load_targets(self) -> list[_ProbeTarget]:
        async with self._session_factory() as session:
            return await session.run_sync(_build_probe_targets)

    def _runtime(self):
        return get_channel_runtime()


def _build_probe_targets(sync_session) -> list[_ProbeTarget]:
    """读取待探测渠道并构造最小文本请求；不支持文本的渠道返回不可探测目标。"""

    channel_crud = ChannelCrud(sync_session)
    registry = get_provider_template_registry()
    factory = get_channel_provider_factory()
    targets: list[_ProbeTarget] = []
    for channel in channel_crud.list_probe_channels():
        route_ids = [route.id for route in channel_crud.list_routes_for_channel(channel_id=channel.id)]
        auto_disabled = channel.auto_disabled_at is not None
        model = _resolve_probe_model(channel_crud, channel.supported_models)
        if model is None:
            targets.append(
                _ProbeTarget(
                    channel_id=channel.id,
                    channel_name=channel.name,
                    auto_disabled=auto_disabled,
                    route_ids=route_ids,
                    provider=None,
                    request_body=None,
                )
            )
            continue
        template = registry.get(model.template_id)
        if template is None:
            continue
        request_body = {
            "model": model.name,
            "messages": [{"role": "user", "content": _PROBE_MESSAGE}],
            "max_tokens": _PROBE_MAX_TOKENS,
        }
        apply_upstream_model_name(request_body, channel.model_mapping.get(model.name))
        request_body.update(deepcopy(channel.param_override))
        try:
            provider = factory.get_frozen_generation_provider(
                {
                    "route_id": str(channel.id),
                    "base_url": channel.base_url,
                    "config": {**template.get("provider_config", {}), **dict(channel.config)},
                },
                provider_type=template["provider_type"],
                api_key=channel.api_key,
            )
        except ProviderError:
            logger.warning("渠道探测目标构造失败 channel_id=%s", channel.id, exc_info=True)
            continue
        targets.append(
            _ProbeTarget(
                channel_id=channel.id,
                channel_name=channel.name,
                auto_disabled=auto_disabled,
                route_ids=route_ids,
                provider=provider,
                request_body=request_body,
            )
        )
    return targets


def _resolve_probe_model(channel_crud: ChannelCrud, supported_models: list[str]):
    """按渠道声明顺序选择第一个启用的 text 模型。"""

    models = {model.name: model for model in channel_crud.list_active_models_by_names(names=supported_models)}
    for name in supported_models:
        model = models.get(name)
        if model is not None and model.model_type == "text":
            return model
    return None


def _apply_auto_state(sync_session, channel_id: UUID, disabled: bool) -> list[UUID] | None:
    """在短事务内切换自动停用状态，返回该渠道的路由标识供运行时重置。"""

    channel_crud = ChannelCrud(sync_session)
    try:
        channel = channel_crud.get_channel_for_update(channel_id=channel_id)
        if channel is None:
            sync_session.rollback()
            return None
        if disabled:
            if not channel.active or channel.auto_disabled_at is not None:
                sync_session.rollback()
                return None
            channel.active = False
            channel.auto_disabled_at = datetime.now(UTC)
            route_ids: list[UUID] = []
        else:
            if channel.auto_disabled_at is None:
                sync_session.rollback()
                return None
            channel.active = True
            channel.auto_disabled_at = None
            route_ids = [route.id for route in channel_crud.list_routes_for_channel(channel_id=channel.id)]
        sync_session.commit()
        return route_ids
    except Exception:
        sync_session.rollback()
        raise
