"""管理员邀请返利 RPC 接口。"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.core.auth import get_admin_user_id
from app.core.database import get_db
from app.modules.affiliate.api.admin_schemas import (
    AdminAffiliateAccrueListResponse,
    AdminAffiliateTransferListResponse,
    AdminAffiliateUserListResponse,
    AdminAffiliateUserOverview,
)
from app.modules.affiliate.application.admin_services import AffiliateAdminService

admin_router = APIRouter(
    prefix="/admin/affiliates",
    tags=["管理员邀请返利"],
    dependencies=[Depends(get_admin_user_id)],
)


@admin_router.get("/records/accrue/list", response_model=AdminAffiliateAccrueListResponse, summary="查询返利产生流水")
def list_affiliate_accrue_records(
    session: Annotated[Session, Depends(get_db)],
    page: int = Query(default=1, ge=1, description="从 1 开始的页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="单页最大返回 100 条"),
) -> dict:
    """分页返回全部返利产生流水及来源订单。"""

    return AffiliateAdminService(session).list_accrue_records(page=page, page_size=page_size)


@admin_router.get(
    "/records/transfer/list", response_model=AdminAffiliateTransferListResponse, summary="查询返利转出流水"
)
def list_affiliate_transfer_records(
    session: Annotated[Session, Depends(get_db)],
    page: int = Query(default=1, ge=1, description="从 1 开始的页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="单页最大返回 100 条"),
) -> dict:
    """分页返回全部返利转入余额流水及额度快照。"""

    return AffiliateAdminService(session).list_transfer_records(page=page, page_size=page_size)


@admin_router.get("/users/list", response_model=AdminAffiliateUserListResponse, summary="查询邀请返利用户")
def list_affiliate_users(
    session: Annotated[Session, Depends(get_db)],
    page: int = Query(default=1, ge=1, description="从 1 开始的页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="单页最大返回 100 条"),
    search: str | None = Query(default=None, max_length=128, description="按用户名或邮箱模糊搜索"),
) -> dict:
    """分页返回拥有邀请档案的用户及其上级和额度。"""

    return AffiliateAdminService(session).list_users(page=page, page_size=page_size, search=search)


@admin_router.get("/users/detail", response_model=AdminAffiliateUserOverview, summary="查询邀请返利用户详情")
def get_affiliate_user_detail(
    session: Annotated[Session, Depends(get_db)],
    user_id: Annotated[UUID, Query(description="目标用户标识")],
) -> dict:
    """返回单个用户的邀请码、有效比例与额度概览。"""

    return AffiliateAdminService(session).get_user_overview(user_id)
