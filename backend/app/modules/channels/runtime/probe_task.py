"""渠道健康探测系统任务 runner。"""

from app.core.config import get_settings
from app.core.database import get_async_session_factory
from app.modules.channels.application.health_probe import ChannelHealthProbeApplicationService
from app.modules.channels.runtime.task_gate import acquire_window
from app.modules.system_tasks.application.services import AsyncSystemTaskApplicationService

_PROBE_TASK_TYPE = "channel_health_probe"


class ChannelHealthProbeSystemTaskRunner:
    """按固定间隔入队并执行渠道最小请求探测。"""

    task_type = _PROBE_TASK_TYPE

    async def schedule(self, service: AsyncSystemTaskApplicationService) -> None:
        settings = get_settings()
        if not settings.routing_runtime_enabled:
            return
        if acquire_window("channel-health-probe", settings.routing_probe_interval_seconds):
            await service.enqueue(task_type=self.task_type)

    async def run(self) -> dict[str, int]:
        return await ChannelHealthProbeApplicationService(get_async_session_factory()).probe_all()
