"""管理员支付配置与合规确认接口，只处理 HTTP 边界和异常映射。"""

from typing import Annotated
from uuid import UUID

from app.core.auth import get_admin_user_id
from app.core.config import get_settings
from app.core.database import get_db
from app.modules.payment.api.payment.schemas import (
    PaymentComplianceConfirmRequest,
    PaymentComplianceConfirmResponse,
    PaymentSettingsRequest,
    PaymentSettingsResponse,
)
from app.modules.payment.application.admin.settings import PaymentSettingsService
from fastapi import APIRouter, Depends, Request
from sqlmodel import Session

router = APIRouter(prefix="/admin/payments", tags=["管理员支付管理"])


@router.post("/compliance/confirm", response_model=PaymentComplianceConfirmResponse, summary="确认支付合规条款")
def confirm_payment_compliance(
    payload: PaymentComplianceConfirmRequest,
    request: Request,
    user_id: Annotated[UUID, Depends(get_admin_user_id)],
    session: Annotated[Session, Depends(get_db)],
) -> dict[str, object]:
    return PaymentSettingsService(session, get_settings()).confirm_current_terms(
        payload.confirmed, user_id, request.client.host if request.client else None
    )


@router.get(
    "/settings/detail",
    response_model=PaymentSettingsResponse,
    dependencies=[Depends(get_admin_user_id)],
    summary="获取支付配置",
)
def get_payment_settings(session: Annotated[Session, Depends(get_db)]) -> dict[str, object]:
    return PaymentSettingsService(session, get_settings()).get_admin_settings()


@router.post(
    "/settings/update",
    response_model=PaymentSettingsResponse,
    dependencies=[Depends(get_admin_user_id)],
    summary="更新支付配置",
)
def update_payment_settings(
    payload: PaymentSettingsRequest, session: Annotated[Session, Depends(get_db)]
) -> dict[str, object]:
    return PaymentSettingsService(session, get_settings()).update_admin_settings(payload.model_dump())
