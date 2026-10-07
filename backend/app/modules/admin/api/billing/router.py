"""管理员账务 HTTP 接口。"""

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlmodel import Session

from app.core.auth import get_admin_user_id
from app.core.database import get_db
from app.modules.admin.api.billing.schemas import (
    AdjustmentRequest,
    RedemptionCodeDetailRequest,
    RedemptionCodeExportRequest,
    RedemptionCodeListRequest,
    RedemptionCodeRequest,
    RedemptionCodeStatusRequest,
    RedemptionCodeUpdateRequest,
)
from app.modules.billing.application.services import BillingApplicationService

router = APIRouter(prefix="/billing", tags=["管理员账务"])


@router.post("/balances/adjust", status_code=201, summary="调整用户余额")
def adjust(
    payload: AdjustmentRequest,
    admin_id: Annotated[UUID, Depends(get_admin_user_id)],
    session: Annotated[Session, Depends(get_db)],
) -> dict:
    return BillingApplicationService(session).adjust_balance(admin_id=admin_id, **payload.model_dump(exclude_none=True))


@router.post("/redemption-codes/create", status_code=201, summary="创建兑换码")
def create_code(
    payload: RedemptionCodeRequest,
    admin_id: Annotated[UUID, Depends(get_admin_user_id)],
    session: Annotated[Session, Depends(get_db)],
) -> dict:
    return BillingApplicationService(session).create_redemption_codes(admin_id=admin_id, **payload.model_dump())


@router.get("/redemption-codes/list", summary="查询兑换码列表")
def list_codes(
    payload: Annotated[RedemptionCodeListRequest, Depends()],
    _: Annotated[UUID, Depends(get_admin_user_id)],
    session: Annotated[Session, Depends(get_db)],
) -> dict:
    return BillingApplicationService(session).list_redemption_codes(**payload.model_dump())


@router.get("/redemption-codes/export", summary="导出兑换码")
def export_codes(
    payload: Annotated[RedemptionCodeExportRequest, Depends()],
    _: Annotated[UUID, Depends(get_admin_user_id)],
    session: Annotated[Session, Depends(get_db)],
) -> Response:
    codes = BillingApplicationService(session).list_redemption_code_values(**payload.model_dump())
    filename = f"redemption-codes-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}.txt"
    return Response(
        content="".join(f"{code}\n" for code in codes),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/redemption-codes/detail", summary="查询兑换码详情")
def get_code(
    payload: Annotated[RedemptionCodeDetailRequest, Depends()],
    _: Annotated[UUID, Depends(get_admin_user_id)],
    session: Annotated[Session, Depends(get_db)],
) -> dict:
    return BillingApplicationService(session).get_redemption_code(payload.code_id)


@router.post("/redemption-codes/update", summary="更新兑换码")
def update_code(
    payload: RedemptionCodeUpdateRequest,
    _: Annotated[UUID, Depends(get_admin_user_id)],
    session: Annotated[Session, Depends(get_db)],
) -> dict:
    return BillingApplicationService(session).update_redemption_code(**payload.model_dump())


@router.post("/redemption-codes/update-status", summary="更新兑换码状态")
def change_code_status(
    payload: RedemptionCodeStatusRequest,
    _: Annotated[UUID, Depends(get_admin_user_id)],
    session: Annotated[Session, Depends(get_db)],
) -> dict:
    return BillingApplicationService(session).change_redemption_code_status(**payload.model_dump())
