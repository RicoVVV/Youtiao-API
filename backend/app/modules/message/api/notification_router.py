"""用户端通知弹窗 RPC HTTP API。"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.core.auth import get_user_id
from app.core.database import get_db
from app.modules.message.api.schemas import NotificationCurrentResponse, NotificationDismissRequest
from app.modules.message.application.services import NotificationService

router = APIRouter(prefix="/notifications", tags=["通知"])


@router.get("/current", response_model=NotificationCurrentResponse, summary="查询当前弹窗通知")
def get_current_notification(
    user_id: Annotated[UUID, Depends(get_user_id)], session: Annotated[Session, Depends(get_db)]
) -> dict:
    return NotificationService(session).current(user_id=user_id)


@router.post("/dismiss", summary="关闭通知")
def dismiss_notification(
    payload: NotificationDismissRequest,
    user_id: Annotated[UUID, Depends(get_user_id)],
    session: Annotated[Session, Depends(get_db)],
) -> dict:
    return NotificationService(session).dismiss(user_id=user_id, **payload.model_dump())
