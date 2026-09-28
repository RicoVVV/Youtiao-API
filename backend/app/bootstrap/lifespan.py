"""应用生命周期组合根，负责 API 进程资源的释放。"""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import get_settings
from app.core.database import dispose_async_database, dispose_database, get_session_factory
from app.infrastructure.http.client import close_async_http_client
from app.modules.channels.runtime.routing_snapshot import RoutingSnapshotInvalidationSubscriber
from app.modules.monitoring.application.runtime import GroupMonitorSystemTaskRunner, ServerMetricSystemTaskRunner
from app.modules.payment.application.admin.settings import PaymentSettingsRuntimeManager
from app.modules.system_tasks.runtime import SystemTaskRuntime
from app.modules.usage.application.runtime import UsageStatisticsSystemTaskRunner
from app.modules.video.application.tasks.runtime import VideoPollSystemTaskRunner


async def _sync_payment_settings(manager: PaymentSettingsRuntimeManager, interval: int) -> None:
    """按周期刷新支付快照；单次失败不终止后台任务。"""
    while True:
        await asyncio.sleep(interval)
        try:
            manager.refresh()
        except Exception:
            logging.getLogger(__name__).exception("支付配置定期同步失败，继续使用旧快照")


async def _listen_for_routing_snapshot_invalidations(subscriber: RoutingSnapshotInvalidationSubscriber) -> None:
    while True:
        try:
            await asyncio.to_thread(subscriber.listen_once)
        except Exception:
            logging.getLogger(__name__).exception("路由快照 Redis 订阅失败，继续重试")
            await asyncio.sleep(1)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """管理 API 进程资源。

    参数：应用实例由 FastAPI 生命周期机制传入，当前不直接使用。
    返回值：向 FastAPI 提供生命周期上下文。
    副作用：进程关闭时释放数据库连接池；数据库迁移由独立 Compose 服务执行。
    """

    settings = get_settings()
    settings.video_result_storage_dir.mkdir(parents=True, exist_ok=True)
    if not settings.video_result_storage_dir.is_dir():
        raise RuntimeError("视频成品目录不可用")
    manager = PaymentSettingsRuntimeManager(get_session_factory(), settings)
    manager.load_initial()
    sync_task = asyncio.create_task(
        _sync_payment_settings(manager, get_settings().payment_settings_sync_interval_seconds)
    )
    routing_subscriber = RoutingSnapshotInvalidationSubscriber()
    routing_listener_task = asyncio.create_task(_listen_for_routing_snapshot_invalidations(routing_subscriber))
    runtime = SystemTaskRuntime(
        [
            VideoPollSystemTaskRunner(),
            UsageStatisticsSystemTaskRunner(),
            GroupMonitorSystemTaskRunner(),
            ServerMetricSystemTaskRunner(),
        ]
    )
    await runtime.start()
    try:
        yield
    finally:
        sync_task.cancel()
        routing_listener_task.cancel()
        await asyncio.gather(sync_task, routing_listener_task, return_exceptions=True)
        await asyncio.to_thread(routing_subscriber.close)
        await runtime.stop()
        await close_async_http_client()
        await dispose_async_database()
        dispose_database()
