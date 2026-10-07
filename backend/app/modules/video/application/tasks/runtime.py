"""视频轮询系统任务 runner。"""

from datetime import UTC, datetime

from app.core.database import get_async_session_factory
from app.modules.system_tasks.application.services import AsyncSystemTaskApplicationService
from app.modules.video.application.materials.metering import cleanup_expired_materials
from app.modules.video.application.tasks.async_runtime import AsyncVideoApplicationService
from app.modules.video.crud.tasks.async_ import AsyncVideoTaskCrud


class VideoPollSystemTaskRunner:
    """负责视频任务轮询：按需入队，执行时轮询上游并维护本地成品。"""

    task_type = "async_task_poll"

    async def schedule(self, service: AsyncSystemTaskApplicationService) -> None:
        """清理过期素材，并在存在待处理视频任务时幂等入队轮询任务。"""

        await cleanup_expired_materials()
        async with get_async_session_factory()() as session:
            video_task_crud = AsyncVideoTaskCrud(session)
            pending = (
                await video_task_crud.has_unfinished_tasks()
                or await video_task_crud.has_succeeded_task_with_reserved_usage()
                or await video_task_crud.has_local_result_maintenance_candidates(expires_before=datetime.now(UTC))
            )
        if pending:
            await service.enqueue(task_type=self.task_type)

    async def run(self) -> dict[str, int]:
        return await AsyncVideoApplicationService(get_async_session_factory()).poll_once()
