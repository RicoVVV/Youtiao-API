"""管理员支付配置与合规确认接口，只处理 HTTP 边界和异常映射。"""

import csv
import io
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from app.core.auth import get_admin_user_id
from app.core.config import get_settings
from app.core.database import get_db
from app.modules.payment.api.admin.schemas import (
    AdminPaymentOrderExportQuery,
    AdminPaymentOrderListQuery,
    AdminPaymentOrderListResponse,
)
from app.modules.payment.api.payment.schemas import (
    PaymentComplianceConfirmRequest,
    PaymentComplianceConfirmResponse,
    PaymentSettingsRequest,
    PaymentSettingsResponse,
)
from app.modules.payment.application.admin.orders import AdminPaymentOrderService
from app.modules.payment.application.admin.settings import PaymentSettingsService
from fastapi import APIRouter, Depends, Request, Response
from sqlmodel import Session

router = APIRouter(prefix="/admin/payments", tags=["管理员支付管理"])

# 支付流水 CSV 的列顺序与中文表头，与导出视图字段一一对应。
_PAYMENT_ORDER_CSV_COLUMNS: tuple[tuple[str, str], ...] = (
    ("order_no", "订单号"),
    ("user_id", "用户ID"),
    ("username", "用户名"),
    ("topup_amount", "充值金额"),
    ("pay_amount", "实付金额"),
    ("payment_channel", "支付渠道"),
    ("payment_method", "支付方式"),
    ("channel_transaction_id", "渠道交易号"),
    ("status", "订单状态"),
    ("created_at", "创建时间"),
    ("paid_at", "支付时间"),
)


@router.get(
    "/orders/list",
    response_model=AdminPaymentOrderListResponse,
    dependencies=[Depends(get_admin_user_id)],
    summary="查询支付流水列表",
)
def list_payment_orders(
    payload: Annotated[AdminPaymentOrderListQuery, Depends()],
    session: Annotated[Session, Depends(get_db)],
) -> dict[str, object]:
    return AdminPaymentOrderService(session).list_orders(**payload.model_dump())


@router.get(
    "/orders/export",
    dependencies=[Depends(get_admin_user_id)],
    summary="导出支付流水",
)
def export_payment_orders(
    payload: Annotated[AdminPaymentOrderExportQuery, Depends()],
    session: Annotated[Session, Depends(get_db)],
) -> Response:
    rows = AdminPaymentOrderService(session).list_export_rows(**payload.model_dump())
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([header for _, header in _PAYMENT_ORDER_CSV_COLUMNS])
    for row in rows:
        writer.writerow([_csv_cell(row[key]) for key, _ in _PAYMENT_ORDER_CSV_COLUMNS])
    filename = f"payment-orders-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}.csv"
    return Response(
        content="\ufeff" + buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _csv_cell(value: object) -> str:
    """将导出视图字段规范化为 CSV 单元格文本。

    作用：统一时间字段的 ISO 8601 输出，并把空值渲染为空字符串。
    使用位置：由支付流水导出路由逐格拼接 CSV 行时调用。
    传入参数：value 为视图字典中的字段值。
    返回参数：返回可直接写入 CSV 的字符串。
    """

    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


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
