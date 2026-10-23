"""分组文本嗅探用例。

管理员切换到嗅探模式后，平台按固定节奏向每个对用户可见的分组发送一条最小文本请求，
结果只写入 ``group_probe_results`` 供监控展示：不产生扣费、不写使用记录，
也不参与渠道熔断、权重衰减与自动禁用。

嗅探仅对文本模型生效；一个分组有多个文本模型时按模型名顺序取第一个可用模型，
再按该分组内的路由权重选择一个启用且健康的渠道。
"""

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
from app.core.database import get_session_factory
from app.modules.channels.application.model_mapping import apply_upstream_model_name
from app.modules.channels.application.probe_request import build_probe_request
from app.modules.channels.application.routing import RoutableChannelBinding, select_channel
from app.modules.channels.crud.channels import ChannelCrud
from app.modules.monitoring.application.traffic_settings import MonitorTrafficSettingsApplicationService
from app.modules.monitoring.application.visibility_settings import MonitorUserVisibilityApplicationService
from app.modules.monitoring.crud.probe_result_crud import GroupProbeResultCrud
from app.modules.monitoring.model import MONITOR_MODE_PROBE, GroupProbeResult
from app.modules.providers.contracts import GenerationProvider, ProviderError
from app.modules.system_settings.application.services import SystemSettingsApplicationService
from app.modules.user.crud.token_group_crud import TokenGroupCrud

logger = logging.getLogger(__name__)

_ERROR_MESSAGE_MAX_LENGTH = 512


@dataclass(frozen=True, slots=True)
class _ProbeTarget:
    """一个分组的最小文本嗅探目标。"""

    group_id: int
    model_id: UUID
    model_name: str
    channel_id: UUID
    channel_name: str
    provider_name: str
    provider: GenerationProvider
    operation: str
    request_body: dict[str, Any]
    timeout_seconds: int


class GroupProbeApplicationService:
    """在嗅探模式下为一轮所有可嗅探分组发送最小文本请求并落库。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def probe_all(self) -> dict[str, int]:
        """执行一轮分组文本嗅探，返回本轮统计。单个分组异常不影响其他分组。"""

        counters = {"probed": 0, "succeeded": 0, "failed": 0, "skipped": 0}
        if await self._load_text_mode() != MONITOR_MODE_PROBE:
            return counters
        targets = await self._load_targets()
        counters["skipped"] = len(targets)
        semaphore = asyncio.Semaphore(get_settings().routing_probe_concurrency)
        results = await asyncio.gather(
            *(self._probe_one(target, semaphore) for target in targets), return_exceptions=True
        )
        for target, result in zip(targets, results, strict=True):
            counters["skipped"] -= 1
            if isinstance(result, BaseException):
                logger.warning("分组文本嗅探异常 group_id=%s", target.group_id, exc_info=result)
                counters["failed"] += 1
                continue
            counters["probed"] += 1
            counters["succeeded" if result else "failed"] += 1
        logger.info("分组文本嗅探完成 %s", counters)
        return counters

    async def _probe_one(self, target: _ProbeTarget, semaphore: asyncio.Semaphore) -> bool:
        async with semaphore:
            started_at = perf_counter()
            succeeded = False
            error_code: str | None = None
            error_message: str | None = None
            try:
                await getattr(target.provider, target.operation)(target.request_body, timeout=target.timeout_seconds)
                succeeded = True
            except ProviderError as exc:
                error_code = exc.code[:64]
                error_message = str(exc)[:_ERROR_MESSAGE_MAX_LENGTH]
                logger.info(
                    "分组文本嗅探失败 group_id=%s channel_id=%s code=%s",
                    target.group_id,
                    target.channel_id,
                    exc.code,
                )
            except Exception as exc:
                error_code = "probe_error"
                error_message = str(exc)[:_ERROR_MESSAGE_MAX_LENGTH]
                logger.warning("分组文本嗅探调用异常 group_id=%s", target.group_id, exc_info=True)
            duration_ms = max(0, round((perf_counter() - started_at) * 1000))
        await asyncio.to_thread(
            self._persist_result,
            target,
            duration_ms,
            succeeded,
            error_code,
            error_message,
        )
        return succeeded

    async def _load_text_mode(self) -> str:
        async with self._session_factory() as session:
            return await session.run_sync(
                lambda sync_session: MonitorTrafficSettingsApplicationService(sync_session).current_text_mode()
            )

    async def _load_targets(self) -> list[_ProbeTarget]:
        async with self._session_factory() as session:
            return await session.run_sync(_build_group_probe_targets)

    def _persist_result(
        self,
        target: _ProbeTarget,
        duration_ms: int,
        succeeded: bool,
        error_code: str | None,
        error_message: str | None,
    ) -> None:
        with get_session_factory()() as session:
            try:
                GroupProbeResultCrud(session).create(
                    GroupProbeResult(
                        completed_at=datetime.now(UTC),
                        token_group_id=target.group_id,
                        model_id=target.model_id,
                        model_name=target.model_name,
                        channel_id=target.channel_id,
                        channel_name=target.channel_name,
                        provider_name=target.provider_name,
                        request_type="text",
                        status="succeeded" if succeeded else "failed",
                        duration_ms=duration_ms,
                        first_token_duration_ms=duration_ms if succeeded else None,
                        error_code=error_code,
                        error_message=error_message,
                    )
                )
                session.commit()
            except Exception:
                session.rollback()
                raise


def _build_group_probe_targets(sync_session) -> list[_ProbeTarget]:
    """为一个对用户可见的分组选择文本模型、可用渠道与最小请求体。"""

    visibility = MonitorUserVisibilityApplicationService(sync_session)
    if "text" not in visibility.visible_request_types():
        return []
    visible_group_ids = visibility.restricted_group_ids()
    groups = [
        group
        for group in TokenGroupCrud(sync_session).list_groups()
        if group.is_active and (visible_group_ids is None or group.id in visible_group_ids)
    ]
    channel_crud = ChannelCrud(sync_session)
    registry = get_provider_template_registry()
    factory = get_channel_provider_factory()
    timeout_seconds = (
        SystemSettingsApplicationService(sync_session, get_settings())
        .read_channel_automation_config()
        .probe_timeout_seconds
    )
    targets: list[_ProbeTarget] = []
    for group in groups:
        model = next(
            (
                candidate
                for candidate in channel_crud.list_active_models_for_groups(group_ids=[group.id])
                if candidate.model_type == "text"
            ),
            None,
        )
        if model is None or not model.template_id:
            continue
        template = registry.get(model.template_id)
        if template is None:
            continue
        rows = channel_crud.list_channels_for_model(model_id=model.id, group_ids=[group.id])
        bindings = [RoutableChannelBinding(binding=route, channel=channel) for route, channel in rows]
        try:
            route = select_channel(bindings)
        except ValueError:
            continue
        channel = route.channel
        probe = build_probe_request(template_id=template["template_id"], model_name=model.name)
        if probe is None:
            logger.warning("分组嗅探模板未登记最小请求 group_id=%s template_id=%s", group.id, model.template_id)
            continue
        request_body = probe.body
        apply_upstream_model_name(request_body, channel.model_mapping.get(model.name))
        request_body.update(deepcopy(channel.param_override))
        try:
            provider = factory.get_frozen_generation_provider(
                {
                    "route_id": str(route.binding.id),
                    "base_url": channel.base_url,
                    "config": {**template.get("provider_config", {}), **dict(channel.config)},
                },
                provider_type=template["provider_type"],
                api_key=channel.api_key,
            )
        except ProviderError:
            logger.warning("分组嗅探目标构造失败 group_id=%s channel_id=%s", group.id, channel.id, exc_info=True)
            continue
        targets.append(
            _ProbeTarget(
                group_id=group.id,
                model_id=model.id,
                model_name=model.name,
                channel_id=channel.id,
                channel_name=channel.name,
                provider_name=template["provider_type"],
                provider=provider,
                operation=probe.operation,
                request_body=request_body,
                timeout_seconds=timeout_seconds,
            )
        )
    return targets
