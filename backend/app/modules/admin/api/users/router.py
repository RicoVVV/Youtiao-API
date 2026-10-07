"""管理员用户 HTTP API，负责账户创建与运营列表查询。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.core.auth import get_admin_user_id
from app.core.database import get_db
from app.modules.admin.api.users.schemas import (
    AdminUserCreateRequest,
    AdminUserCreateResponse,
    AdminUserListItem,
    AdminUserListResponse,
)
from app.modules.admin.application.users.services import AdminUserApplicationService
from app.modules.user.application.auth.services import AuthApplicationService

router = APIRouter(prefix="/admin/user", tags=["管理员用户与令牌"])


@router.post(
    "/create", response_model=AdminUserCreateResponse, dependencies=[Depends(get_admin_user_id)], summary="创建用户"
)
def create_user(
    payload: AdminUserCreateRequest, session: Annotated[Session, Depends(get_db)]
) -> AdminUserCreateResponse:
    result = AuthApplicationService(session).register_user(**payload.model_dump(), skip_email_verification=True)
    return AdminUserCreateResponse(user_id=result.user.id, username=result.user.username)


@router.get(
    "/list", response_model=AdminUserListResponse, dependencies=[Depends(get_admin_user_id)], summary="分页查询用户"
)
def list_users(
    session: Annotated[Session, Depends(get_db)],
    page: int = Query(default=1, ge=1, description="从 1 开始的页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="单页最大返回 100 条"),
) -> AdminUserListResponse:
    """分页返回管理员可见的用户安全信息和运营统计。"""

    result = AdminUserApplicationService(session).list_users(page=page, page_size=page_size)
    return AdminUserListResponse(
        items=[
            AdminUserListItem(
                id=item.id,
                username=item.username,
                is_active=item.is_active,
                is_admin=item.is_admin,
                created_at=item.created_at,
                balance=item.balance,
                usage=item.usage,
                active_lease_count=item.active_lease_count,
            )
            for item in result.users
        ],
        total=result.total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/by-username",
    response_model=AdminUserListItem,
    dependencies=[Depends(get_admin_user_id)],
    summary="按用户名查询用户",
)
def get_user_by_username(
    session: Annotated[Session, Depends(get_db)],
    username: str = Query(..., min_length=1, max_length=128, description="精确用户名"),
) -> AdminUserListItem:
    item = AdminUserApplicationService(session).get_user_by_username(username=username)
    return AdminUserListItem(
        id=item.id,
        username=item.username,
        is_active=item.is_active,
        is_admin=item.is_admin,
        created_at=item.created_at,
        balance=item.balance,
        usage=item.usage,
        active_lease_count=item.active_lease_count,
    )
