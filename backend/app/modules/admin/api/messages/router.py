"""管理员消息 RPC HTTP API。

本模块只处理管理员鉴权、请求校验与响应组装；消息维护规则由应用服务负责。
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.core.auth import get_admin_user_id
from app.core.database import get_db
from app.modules.admin.api.messages.schemas import (
    AdminMessageCreateRequest,
    AdminMessageDeleteRequest,
    AdminMessageListResponse,
    AdminMessageResponse,
    AdminMessageStatusRequest,
    AdminMessageUpdateRequest,
)
from app.modules.admin.application.message_service import AdminMessageApplicationService
from app.modules.message.model import MessageType

router = APIRouter(prefix="/admin/messages", tags=["管理员消息"])


@router.get(
    "/list",
    response_model=AdminMessageListResponse,
    dependencies=[Depends(get_admin_user_id)],
    summary="查询消息列表",
)
def list_messages(
    session: Annotated[Session, Depends(get_db)],
    keyword: Annotated[str | None, Query(max_length=255)] = None,
    message_type: Annotated[MessageType | None, Query(alias="type")] = None,
    is_active: Annotated[bool | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict:
    return AdminMessageApplicationService(session).list_page(
        keyword=keyword,
        message_type=message_type,
        is_active=is_active,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/detail",
    response_model=AdminMessageResponse,
    dependencies=[Depends(get_admin_user_id)],
    summary="查询消息详情",
)
def get_message_detail(session: Annotated[Session, Depends(get_db)], message_id: Annotated[UUID, Query()]) -> dict:
    return AdminMessageApplicationService(session).get_detail(message_id)


@router.post(
    "/create",
    response_model=AdminMessageResponse,
    summary="创建消息",
)
def create_message(
    payload: AdminMessageCreateRequest,
    created_by: Annotated[UUID, Depends(get_admin_user_id)],
    session: Annotated[Session, Depends(get_db)],
) -> dict:
    return AdminMessageApplicationService(session).create(payload.model_dump(), created_by=created_by)


@router.post(
    "/update",
    response_model=AdminMessageResponse,
    dependencies=[Depends(get_admin_user_id)],
    summary="更新消息",
)
def update_message(payload: AdminMessageUpdateRequest, session: Annotated[Session, Depends(get_db)]) -> dict:
    return AdminMessageApplicationService(session).update(payload.model_dump(exclude_unset=True))


@router.post(
    "/update-status",
    response_model=AdminMessageResponse,
    dependencies=[Depends(get_admin_user_id)],
    summary="更新消息状态",
)
def update_message_status(payload: AdminMessageStatusRequest, session: Annotated[Session, Depends(get_db)]) -> dict:
    return AdminMessageApplicationService(session).update_status(**payload.model_dump())


@router.post(
    "/delete",
    dependencies=[Depends(get_admin_user_id)],
    summary="删除消息",
)
def delete_message(payload: AdminMessageDeleteRequest, session: Annotated[Session, Depends(get_db)]) -> dict:
    AdminMessageApplicationService(session).delete(payload.message_id)
    return {"success": True}
