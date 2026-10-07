"""管理员用户模型并发 HTTP API，负责覆盖维护与错误映射。"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.core.auth import get_admin_user_id
from app.core.database import get_db
from app.modules.admin.api.concurrency.schemas import (
    AdminUserModelConcurrencyOverrideRequest,
    AdminUserModelConcurrencyOverrideResponse,
    AdminUserModelConcurrencyUsageResponse,
)
from app.modules.admin.application.concurrency.services import AdminConcurrencyApplicationService

router = APIRouter(prefix="/user-model-concurrency", tags=["管理员并发与模型分组"])


@router.get(
    "/list",
    response_model=AdminUserModelConcurrencyUsageResponse,
    dependencies=[Depends(get_admin_user_id)],
    summary="查询用户模型并发配置",
)
def list_user_model_concurrency(
    user_id: Annotated[UUID, Query()], session: Annotated[Session, Depends(get_db)]
) -> dict:
    return AdminConcurrencyApplicationService(session).user_model_usage(user_id=user_id)


@router.post(
    "/update",
    response_model=AdminUserModelConcurrencyOverrideResponse,
    dependencies=[Depends(get_admin_user_id)],
    summary="更新用户模型并发覆盖",
)
def update_user_model_concurrency(
    payload: AdminUserModelConcurrencyOverrideRequest, session: Annotated[Session, Depends(get_db)]
) -> object:
    return AdminConcurrencyApplicationService(session).save_override(**payload.model_dump())
