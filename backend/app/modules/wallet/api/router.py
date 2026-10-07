"""钱包 HTTP 接口。"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.core.auth import get_user_id
from app.core.database import get_db
from app.modules.wallet.api.schemas import RechargeOrderRequest
from app.modules.wallet.application.services import WalletApplicationService

router = APIRouter(prefix="/wallet", tags=["用户钱包"])


@router.get("/detail", summary="查询钱包详情")
def get_wallet_detail(
    user_id: Annotated[UUID, Depends(get_user_id)], session: Annotated[Session, Depends(get_db)]
) -> dict:
    return WalletApplicationService(session).get_wallet_detail(user_id)


@router.get("/balance-records/list", summary="查询余额变动明细")
def list_balance_records(
    user_id: Annotated[UUID, Depends(get_user_id)], session: Annotated[Session, Depends(get_db)]
) -> list[dict]:
    return WalletApplicationService(session).list_balance_record_views(user_id)


@router.get("/recharge-orders/list", summary="查询充值订单列表")
def list_recharge_orders(
    user_id: Annotated[UUID, Depends(get_user_id)], session: Annotated[Session, Depends(get_db)]
) -> list[dict]:
    return WalletApplicationService(session).list_recharge_order_views(user_id)


@router.post("/recharge-orders/create", status_code=201, summary="创建充值订单")
def create_recharge_order(
    payload: RechargeOrderRequest,
    user_id: Annotated[UUID, Depends(get_user_id)],
    session: Annotated[Session, Depends(get_db)],
) -> dict:
    return WalletApplicationService(session).create_recharge_order(user_id=user_id, **payload.model_dump())
