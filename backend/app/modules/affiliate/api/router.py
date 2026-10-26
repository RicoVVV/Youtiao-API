"""邀请返利用户端 RPC 接口。"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.core.auth import get_user_id, require_sidebar_module
from app.core.database import get_db
from app.modules.affiliate.api.schemas import (
    AffiliateDetailResponse,
    AffiliateInviteeListResponse,
    AffiliateLedgerListResponse,
    AffiliateTransferResponse,
)
from app.modules.affiliate.application.services import AffiliateApplicationService

router = APIRouter(
    prefix="/affiliate",
    tags=["邀请返利"],
    dependencies=[Depends(require_sidebar_module("affiliate"))],
)


@router.get("/detail", response_model=AffiliateDetailResponse, summary="查询邀请返利详情")
def get_affiliate_detail(
    user_id: Annotated[UUID, Depends(get_user_id)], session: Annotated[Session, Depends(get_db)]
) -> dict:
    """返回邀请码、邀请链接、有效返利比例、注册赠送额度、额度与被邀请人摘要。"""

    return AffiliateApplicationService(session).get_detail(user_id)


@router.get("/invitees/list", response_model=AffiliateInviteeListResponse, summary="查询被邀请人列表")
def list_affiliate_invitees(
    user_id: Annotated[UUID, Depends(get_user_id)],
    session: Annotated[Session, Depends(get_db)],
    page: int = Query(default=1, ge=1, description="从 1 开始的页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="单页最大返回 100 条"),
) -> dict:
    """分页返回当前用户邀请的用户及其累计返利贡献。"""

    return AffiliateApplicationService(session).list_invitees(user_id, page=page, page_size=page_size)


@router.get("/records/list", response_model=AffiliateLedgerListResponse, summary="查询邀请返利流水")
def list_affiliate_records(
    user_id: Annotated[UUID, Depends(get_user_id)],
    session: Annotated[Session, Depends(get_db)],
    page: int = Query(default=1, ge=1, description="从 1 开始的页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="单页最大返回 100 条"),
) -> dict:
    """分页返回返利产生与转入余额流水。"""

    return AffiliateApplicationService(session).list_records(user_id, page=page, page_size=page_size)


@router.post("/quota/transfer", response_model=AffiliateTransferResponse, summary="邀请返利转入余额")
def transfer_affiliate_quota(
    user_id: Annotated[UUID, Depends(get_user_id)], session: Annotated[Session, Depends(get_db)]
) -> dict:
    """把全部可用返利额度转入钱包余额；无可用额度时返回 422。"""

    return AffiliateApplicationService(session).transfer_quota(user_id)
