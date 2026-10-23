"""渠道健康探测系统任务 runner。"""

from app.core.channel_automation import ChannelAutomationConfig
from app.core.config import get_settings
from app.core.database import get_async_session_factory
from app.modules.channels.application.health_probe import ChannelHealthProbeApplicationService
from app.modules.channels.runtime.task_gate import acquire_window
from app.modules.system_settings.application.services import SystemSettingsApplicationService
from app.modules.system_tasks.application.services import AsyncSystemTaskApplicationService

_PROBE_TASK_TYPE = "channel_health_probe"


class ChannelHealthProbeSystemTaskRunner:
    """按管理员配置的间隔入队并执行渠道最小请求探测。"""

    task_type = _PROBE_TASK_TYPE

    async def schedule(self, service: AsyncSystemTaskApplicationService) -> None:
        settings = get_settings()
        config = await _refresh_automation_config()
        if not settings.routing_runtime_enabled:
            return
        if not config.probe_enabled:
            return
        if acquire_window("channel-health-probe", config.probe_interval_seconds):
            await service.enqueue(task_type=self.task_type)

    async def run(self) -> dict[str, int]:
        return await ChannelHealthProbeApplicationService(get_async_session_factory()).probe_all()


async def _refresh_automation_config() -> ChannelAutomationConfig:
    """每轮调度刷新一次管理员配置，兼顾多实例生效与请求链路读取缓存的开销。"""

    session_factory = get_async_session_factory()
    async with session_factory() as session:
        return await session.run_sync(
            lambda sync_session: SystemSettingsApplicationService(
                sync_session, get_settings()
            ).refresh_channel_automation_config()
        )
