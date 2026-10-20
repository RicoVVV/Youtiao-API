"""管理员通知 RPC HTTP API。

本模块只处理管理员鉴权、请求校验与响应组装；通知维护规则由应用服务负责。
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.core.auth import get_admin_user_id
from app.core.database import get_db
from app.modules.admin.api.notifications.schemas import (
    AdminNotificationCreateRequest,
    AdminNotificationDeleteRequest,
    AdminNotificationListResponse,
    AdminNotificationResponse,
    AdminNotificationStatusRequest,
    AdminNotificationUpdateRequest,
)
from app.modules.admin.application.notification_service import AdminNotificationApplicationService

router = APIRouter(prefix="/admin/notifications", tags=["管理员通知"])


@router.get(
    "/list",
    response_model=AdminNotificationListResponse,
    dependencies=[Depends(get_admin_user_id)],
    summary="查询通知列表",
)
def list_notifications(
    session: Annotated[Session, Depends(get_db)],
    keyword: Annotated[str | None, Query(max_length=255)] = None,
    is_active: Annotated[bool | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict:
    return AdminNotificationApplicationService(session).list_page(
        keyword=keyword, is_active=is_active, page=page, page_size=page_size
    )


@router.get(
    "/detail",
    response_model=AdminNotificationResponse,
    dependencies=[Depends(get_admin_user_id)],
    summary="查询通知详情",
)
def get_notification_detail(
    session: Annotated[Session, Depends(get_db)], notification_id: Annotated[UUID, Query()]
) -> dict:
    return AdminNotificationApplicationService(session).get_detail(notification_id)


@router.post(
    "/create",
    response_model=AdminNotificationResponse,
    summary="创建通知",
)
def create_notification(
    payload: AdminNotificationCreateRequest,
    created_by: Annotated[UUID, Depends(get_admin_user_id)],
    session: Annotated[Session, Depends(get_db)],
) -> dict:
    return AdminNotificationApplicationService(session).create(payload.model_dump(), created_by=created_by)


@router.post(
    "/update",
    response_model=AdminNotificationResponse,
    dependencies=[Depends(get_admin_user_id)],
    summary="更新通知",
)
def update_notification(payload: AdminNotificationUpdateRequest, session: Annotated[Session, Depends(get_db)]) -> dict:
    return AdminNotificationApplicationService(session).update(payload.model_dump(exclude_unset=True))


@router.post(
    "/update-status",
    response_model=AdminNotificationResponse,
    dependencies=[Depends(get_admin_user_id)],
    summary="更新通知状态",
)
def update_notification_status(
    payload: AdminNotificationStatusRequest, session: Annotated[Session, Depends(get_db)]
) -> dict:
    return AdminNotificationApplicationService(session).update_status(**payload.model_dump())


@router.post(
    "/delete",
    dependencies=[Depends(get_admin_user_id)],
    summary="删除通知",
)
def delete_notification(payload: AdminNotificationDeleteRequest, session: Annotated[Session, Depends(get_db)]) -> dict:
    AdminNotificationApplicationService(session).delete(payload.notification_id)
    return {"success": True}
