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
from app.core.channel_automation import ChannelAutomationConfig
from app.core.config import get_settings
from app.modules.channels.application.lifecycle import set_channel_auto_disabled
from app.modules.channels.application.model_mapping import apply_upstream_model_name
from app.modules.channels.application.probe_request import build_probe_request
from app.modules.channels.crud.channels import ChannelCrud
from app.modules.channels.runtime.channel_runtime import ProbeRuntimeResult, get_channel_runtime
from app.modules.providers.contracts import GenerationProvider, ProviderError
from app.modules.system_settings.application.services import SystemSettingsApplicationService

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _ProbeTarget:
    """一个渠道的最小探测目标；``provider`` 为空表示该渠道没有可探测的文本模型。"""

    channel_id: UUID
    channel_name: str
    auto_disabled: bool
    route_ids: list[UUID]
    provider: GenerationProvider | None
    operation: str | None
    request_body: dict[str, Any] | None


class ChannelHealthProbeApplicationService:
    """对启用渠道与自动停用渠道执行最小请求探测，并驱动渠道生命周期。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._settings = get_settings()

    async def probe_all(self) -> dict[str, int]:
        """执行一轮探测，返回本轮统计。单渠道异常不影响其他渠道。"""

        config = await self._load_automation_config()
        counters = {"probed": 0, "succeeded": 0, "failed": 0, "disabled": 0, "enabled": 0, "skipped": 0}
        if not config.probe_enabled:
            logger.info("管理员已关闭定时渠道探测，跳过本轮")
            return counters
        targets = await self._load_targets()
        semaphore = asyncio.Semaphore(self._settings.routing_probe_concurrency)
        results = await asyncio.gather(
            *(self._probe_one(target, semaphore, config) for target in targets), return_exceptions=True
        )
        for target, result in zip(targets, results, strict=True):
            if isinstance(result, BaseException):
                logger.warning("渠道健康探测异常 channel_id=%s", target.channel_id, exc_info=result)
                counters["failed"] += 1
                continue
            counters[result] += 1
        logger.info("渠道健康探测完成 %s", counters)
        return counters

    async def _probe_one(
        self, target: _ProbeTarget, semaphore: asyncio.Semaphore, config: ChannelAutomationConfig
    ) -> str:
        if target.provider is None or target.operation is None or target.request_body is None:
            return "skipped"
        probe_call = getattr(target.provider, target.operation, None)
        if not callable(probe_call):
            return "skipped"
        async with semaphore:
            if await asyncio.to_thread(self._should_skip_disabled, target):
                return "skipped"
            started_at_counter = perf_counter()
            succeeded = False
            try:
                await probe_call(target.request_body, timeout=config.probe_timeout_seconds)
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
        applied = await self._apply_lifecycle(target, succeeded=succeeded, runtime=runtime_result, config=config)
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
        self,
        target: _ProbeTarget,
        *,
        succeeded: bool,
        runtime: ProbeRuntimeResult,
        config: ChannelAutomationConfig,
    ) -> str | None:
        if (
            config.auto_disable_enabled
            and not succeeded
            and not target.auto_disabled
            and runtime.probe_fails >= self._settings.routing_probe_failure_threshold
        ):
            disabled = await set_channel_auto_disabled(
                self._session_factory, channel_id=target.channel_id, disabled=True
            )
            return "disabled" if disabled else None
        if (
            config.auto_enable_enabled
            and succeeded
            and target.auto_disabled
            and runtime.probe_successes >= self._settings.routing_probe_recovery_threshold
        ):
            enabled = await set_channel_auto_disabled(
                self._session_factory, channel_id=target.channel_id, disabled=False
            )
            return "enabled" if enabled else None
        return None

    async def _load_targets(self) -> list[_ProbeTarget]:
        async with self._session_factory() as session:
            return await session.run_sync(_build_probe_targets)

    async def _load_automation_config(self) -> ChannelAutomationConfig:
        async with self._session_factory() as session:
            return await session.run_sync(_refresh_automation_config)

    def _runtime(self):
        return get_channel_runtime()


def _refresh_automation_config(sync_session) -> ChannelAutomationConfig:
    """读取管理员渠道自动化配置并刷新进程内缓存，保证多实例部署下按分钟级生效。"""

    service = SystemSettingsApplicationService(sync_session, get_settings())
    return service.refresh_channel_automation_config()


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
                    operation=None,
                    request_body=None,
                )
            )
            continue
        template = registry.get(model.template_id)
        if template is None:
            continue
        probe = build_probe_request(template_id=template["template_id"], model_name=model.name)
        if probe is None:
            logger.warning("渠道探测模板未登记最小请求 channel_id=%s template_id=%s", channel.id, model.template_id)
            continue
        request_body = probe.body
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
                operation=probe.operation,
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
