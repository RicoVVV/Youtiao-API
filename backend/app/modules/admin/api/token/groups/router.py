"""管理员 Token 分组 RPC HTTP API。

本模块只处理管理员鉴权、请求校验、事务边界和业务错误映射；分组维护规则由应用服务负责。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.core.auth import get_admin_user_id
from app.core.database import get_db
from app.modules.admin.api.token.groups.schemas import (
    AdminTokenGroupCreateRequest,
    AdminTokenGroupDeleteRequest,
    AdminTokenGroupListResponse,
    AdminTokenGroupResponse,
    AdminTokenGroupUpdateRequest,
)
from app.modules.admin.application.token_group_service import AdminTokenGroupApplicationService

router = APIRouter(prefix="/admin/token/groups", tags=["管理员令牌分组"])


@router.get(
    "/list",
    response_model=AdminTokenGroupListResponse | list[AdminTokenGroupResponse],
    dependencies=[Depends(get_admin_user_id)],
    summary="查询 Token 分组",
)
def list_token_groups(
    session: Annotated[Session, Depends(get_db)],
    group_id: Annotated[int | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict | list[dict]:
    if group_id is None:
        total, groups = AdminTokenGroupApplicationService(session).list_groups_page(page, page_size)
        return AdminTokenGroupListResponse(items=groups, total=total, page=page, page_size=page_size).model_dump()
    return [AdminTokenGroupApplicationService(session).get_group(group_id)]


@router.post(
    "/create",
    response_model=AdminTokenGroupResponse,
    dependencies=[Depends(get_admin_user_id)],
    summary="创建 Token 分组",
)
def create_token_group(payload: AdminTokenGroupCreateRequest, session: Annotated[Session, Depends(get_db)]) -> dict:
    return AdminTokenGroupApplicationService(session).create_group(**payload.model_dump())


@router.post(
    "/update",
    response_model=AdminTokenGroupResponse,
    dependencies=[Depends(get_admin_user_id)],
    summary="更新 Token 分组",
)
def update_token_group(payload: AdminTokenGroupUpdateRequest, session: Annotated[Session, Depends(get_db)]) -> dict:
    return AdminTokenGroupApplicationService(session).update_group(**payload.model_dump())


@router.post("/delete", dependencies=[Depends(get_admin_user_id)], summary="删除 Token 分组")
def delete_token_group(payload: AdminTokenGroupDeleteRequest, session: Annotated[Session, Depends(get_db)]) -> dict:
    AdminTokenGroupApplicationService(session).delete_group(**payload.model_dump())
    return {"success": True}
