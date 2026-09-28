"""管理员视频任务 HTTP API，负责鉴权、错误映射和事务提交。"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.core.auth import get_admin_user_id
from app.core.database import get_db
from app.modules.admin.api.videos.schemas import AdminCancelVideoTaskRequest
from app.modules.admin.application.videos.services import AdminVideoApplicationService
from app.modules.video.api.schemas import VideoTaskResponse
from app.modules.video.application.tasks.creation import to_task_data

router = APIRouter(prefix="/videos", tags=["管理员视频任务"])


@router.post("/cancel", response_model=VideoTaskResponse, summary="取消视频任务")
async def cancel_video_task_route(
    payload: AdminCancelVideoTaskRequest,
    admin_id: Annotated[UUID, Depends(get_admin_user_id)],
    session: Annotated[Session, Depends(get_db)],
) -> VideoTaskResponse:
    task = await AdminVideoApplicationService(session).cancel_task(**payload.model_dump(), admin_id=str(admin_id))
    return VideoTaskResponse.from_task_data(to_task_data(task))
