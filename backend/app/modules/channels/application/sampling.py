"""渠道运行时趋势采样：按分钟桶聚合运行时状态并落库。"""

import logging
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.modules.channels.crud.channels import ChannelCrud
from app.modules.channels.crud.samples import ChannelRuntimeSampleCrud
from app.modules.channels.runtime.channel_runtime import get_channel_runtime

logger = logging.getLogger(__name__)

_WEIGHT_QUANT = Decimal("0.01")
_RATE_QUANT = Decimal("0.0001")


class ChannelRuntimeSamplingApplicationService:
    """把当前运行时状态按渠道写入分钟级趋势采样。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._settings = get_settings()

    async def sample_once(self) -> dict[str, int]:
        """执行一次采样并清理超期数据，返回写入与删除行数。"""

        async with self._session_factory() as session:
            return await session.run_sync(_sample_channels, self._settings)


def _sample_channels(sync_session, settings) -> dict[str, int]:
    channel_crud = ChannelCrud(sync_session)
    sample_crud = ChannelRuntimeSampleCrud(sync_session)
    rows = channel_crud.list_channels_with_routes()
    if not rows:
        removed = sample_crud.delete_expired(
            before=datetime.now(UTC) - timedelta(days=settings.routing_sample_retention_days)
        )
        sync_session.commit()
        return {"sampled_channels": 0, "removed_samples": removed}

    grouped = defaultdict(list)
    channel_by_id = {}
    for channel, route in rows:
        grouped[channel.id].append(route)
        channel_by_id[channel.id] = channel

    runtime = get_channel_runtime()
    route_states: dict = {}
    redis_available = True
    try:
        route_states = runtime.read_route_states([route.id for _, route in rows])
    except Exception:
        redis_available = False
        logger.warning("渠道趋势采样读取路由运行时状态失败，本轮使用初始权重", exc_info=True)

    now = datetime.now(UTC)
    bucket_start = now.replace(second=0, microsecond=0)
    written = 0
    for channel_id, routes in grouped.items():
        channel = channel_by_id[channel_id]
        weights: list[float] = []
        success_rates: list[float] = []
        latencies: list[float] = []
        for route in routes:
            state = route_states.get(route.id) or {}
            weight = _float_or_none(state.get("w"))
            weights.append(weight if weight is not None else float(route.weight))
            success_rate = _float_or_none(state.get("sr"))
            if success_rate is not None:
                success_rates.append(success_rate)
            latency = _float_or_none(state.get("lat"))
            if latency is not None:
                latencies.append(latency)
        channel_state: dict = {}
        if redis_available:
            try:
                channel_state = runtime.read_channel_state(channel_id)
            except Exception:
                redis_available = False
                logger.warning("渠道趋势采样读取熔断状态失败，后续渠道按默认状态处理", exc_info=True)
        sample_crud.upsert(
            channel_id=channel_id,
            bucket_start=bucket_start,
            effective_weight=Decimal(str(round(sum(weights) / len(weights), 2))).quantize(_WEIGHT_QUANT),
            success_rate=(
                Decimal(str(round(sum(success_rates) / len(success_rates), 4))).quantize(_RATE_QUANT)
                if success_rates
                else None
            ),
            average_latency_ms=round(sum(latencies) / len(latencies)) if latencies else None,
            circuit_state=str(channel_state.get("state") or "closed"),
            active=channel.active,
        )
        written += 1
    removed = sample_crud.delete_expired(before=now - timedelta(days=settings.routing_sample_retention_days))
    sync_session.commit()
    return {"sampled_channels": written, "removed_samples": removed}


def _float_or_none(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
