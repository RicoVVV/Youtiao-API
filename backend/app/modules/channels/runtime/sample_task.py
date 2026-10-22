"""渠道运行时趋势采样系统任务 runner。"""

from app.core.config import get_settings
from app.core.database import get_async_session_factory
from app.modules.channels.application.sampling import ChannelRuntimeSamplingApplicationService
from app.modules.channels.runtime.task_gate import acquire_window
from app.modules.system_tasks.application.services import AsyncSystemTaskApplicationService

_SAMPLE_TASK_TYPE = "channel_runtime_sample"


class ChannelRuntimeSampleSystemTaskRunner:
    """按固定间隔入队并执行渠道运行时趋势采样。"""

    task_type = _SAMPLE_TASK_TYPE

    async def schedule(self, service: AsyncSystemTaskApplicationService) -> None:
        settings = get_settings()
        if not settings.routing_runtime_enabled:
            return
        if acquire_window("channel-runtime-sample", settings.routing_sample_interval_seconds):
            await service.enqueue(task_type=self.task_type)

    async def run(self) -> dict[str, int]:
        return await ChannelRuntimeSamplingApplicationService(get_async_session_factory()).sample_once()
