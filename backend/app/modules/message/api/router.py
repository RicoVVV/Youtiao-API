"""用户端消息与统一收件箱 RPC HTTP API。"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.core.auth import get_user_id
from app.core.database import get_db
from app.modules.message.api.schemas import (
    InboxListResponse,
    InboxMessageDetail,
    InboxNotificationDetail,
    InboxUnreadCountResponse,
    MessageMarkAllReadResponse,
    MessageMarkReadResponse,
    MessageReadRequest,
)
from app.modules.message.application.services import InboxCategory, InboxService, MessageService
from app.modules.message.model import MessageType

router = APIRouter(prefix="/messages", tags=["消息"])


@router.get("/list", response_model=InboxListResponse, summary="查询收件箱列表")
def list_inbox(
    user_id: Annotated[UUID, Depends(get_user_id)],
    session: Annotated[Session, Depends(get_db)],
    category: Annotated[InboxCategory, Query()] = InboxCategory.message,
    message_type: Annotated[MessageType | None, Query(alias="type")] = None,
    unread_only: Annotated[bool, Query()] = False,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict:
    return InboxService(session).list_page(
        user_id=user_id,
        category=category,
        message_type=message_type,
        unread_only=unread_only,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/detail",
    response_model=InboxMessageDetail | InboxNotificationDetail,
    summary="查询收件箱详情",
)
def get_inbox_detail(
    user_id: Annotated[UUID, Depends(get_user_id)],
    session: Annotated[Session, Depends(get_db)],
    category: Annotated[InboxCategory, Query()],
    target_id: Annotated[UUID, Query(alias="id")],
) -> dict:
    return InboxService(session).get_detail(user_id=user_id, category=category, target_id=target_id)


@router.get("/unread-count", response_model=InboxUnreadCountResponse, summary="查询收件箱未读数量")
def get_inbox_unread_count(
    user_id: Annotated[UUID, Depends(get_user_id)], session: Annotated[Session, Depends(get_db)]
) -> dict:
    return InboxService(session).unread_counts(user_id=user_id)


@router.post("/mark-read", response_model=MessageMarkReadResponse, summary="标记消息已读")
def mark_message_read(
    payload: MessageReadRequest,
    user_id: Annotated[UUID, Depends(get_user_id)],
    session: Annotated[Session, Depends(get_db)],
) -> dict:
    return MessageService(session).mark_read(user_id=user_id, **payload.model_dump())


@router.post("/mark-all-read", response_model=MessageMarkAllReadResponse, summary="全部标记消息为已读")
def mark_all_messages_read(
    user_id: Annotated[UUID, Depends(get_user_id)], session: Annotated[Session, Depends(get_db)]
) -> dict:
    return MessageService(session).mark_all_read(user_id=user_id)
