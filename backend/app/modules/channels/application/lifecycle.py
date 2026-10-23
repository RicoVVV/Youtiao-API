"""渠道自动停用与自动启用的生命周期操作。

健康探测与真实请求失败共用同一套状态切换逻辑，保证自动停用、自动恢复与管理台人工操作之间
不会互相覆盖，并在状态变化后让路由快照立即失效。
"""

import asyncio
import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.channels.application.failures import should_auto_disable_channel
from app.modules.channels.crud.channels import ChannelCrud
from app.modules.channels.runtime.channel_runtime import get_channel_runtime
from app.modules.channels.runtime.routing_snapshot import publish_routing_snapshot_invalidation
from app.modules.providers.contracts import ProviderError

logger = logging.getLogger(__name__)


async def set_channel_auto_disabled(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    channel_id: UUID,
    disabled: bool,
) -> bool:
    """在短事务内切换自动停用状态，返回是否实际发生状态变化。"""

    async with session_factory() as session:
        route_ids = await session.run_sync(_apply_auto_state, channel_id, disabled)
    if route_ids is None:
        return False
    try:
        if not disabled:
            await asyncio.to_thread(get_channel_runtime().reset_channel, channel_id=channel_id, route_ids=route_ids)
    except Exception:
        logger.warning("渠道运行时状态重置失败 channel_id=%s", channel_id, exc_info=True)
    publish_routing_snapshot_invalidation()
    logger.warning("渠道已%s channel_id=%s", "自动停用" if disabled else "自动恢复启用", channel_id)
    return True


async def auto_disable_channel_if_needed(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    channel_id: UUID,
    error: ProviderError,
) -> bool:
    """真实请求失败命中管理员配置的状态码或关键词时立即自动禁用渠道。"""

    if not should_auto_disable_channel(error):
        return False
    return await set_channel_auto_disabled(session_factory, channel_id=channel_id, disabled=True)


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
