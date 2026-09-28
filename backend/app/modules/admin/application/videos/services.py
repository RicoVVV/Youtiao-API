"""管理员视频任务应用服务，复用视频领域取消流程而不承载 HTTP 细节。"""

from uuid import UUID

from sqlmodel import Session

from app.modules.video.application.tasks.creation import VideoApplicationService
from app.modules.video.model.video_task import VideoTask


class AdminVideoApplicationService:
    def __init__(self, session: Session) -> None:
        self._session = session

    async def cancel_task(self, *, task_id: UUID, admin_id: str, reason: str) -> VideoTask:
        return await VideoApplicationService(self._session).cancel_task_by_admin(
            task_id=task_id, admin_id=admin_id, reason=reason
        )
