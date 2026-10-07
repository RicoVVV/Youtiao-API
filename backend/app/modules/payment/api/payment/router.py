"""用户支付 HTTP 路由，接收创建订单请求并委托不同支付渠道服务处理。"""

import logging
from typing import Annotated
from urllib.parse import parse_qsl
from uuid import UUID

from app.core.auth import get_user_id
from app.core.database import get_db
from app.modules.payment.api.payment.schemas import (
    OrderStatusResponse,
    PaidRechargeOrderListResponse,
    PaymentQuoteRequest,
    PaymentQuoteResponse,
    PaymentTopupResponse,
    ProviderOrderRequest,
    ProviderOrderResponse,
    StripeProviderOrderResponse,
)
from app.modules.payment.application.payment.alipay import PaymentApplicationService
from app.modules.payment.application.payment.epay import EpayPaymentApplicationService
from app.modules.payment.application.payment.orders import PaymentOrderQueryService
from app.modules.payment.application.payment.stripe import StripePaymentApplicationService
from app.modules.payment.application.quote import PaymentQuoteApplicationService
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse, Response
from sqlmodel import Session

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/payments", tags=["用户支付"])
_MAX_CALLBACK_BODY = 64 * 1024
_MAX_CALLBACK_FIELDS = 32
_MAX_STRIPE_BODY_SIZE = 1024 * 1024


@router.get("/topups/detail", response_model=PaymentTopupResponse, summary="获取充值配置")
def topup_info(
    _: Annotated[UUID, Depends(get_user_id)], session: Annotated[Session, Depends(get_db)]
) -> dict[str, object]:
    return PaymentApplicationService(session).get_topup_info()


@router.post(
    "/quote", response_model=PaymentQuoteResponse, response_model_exclude_none=True, summary="统一试算支付金额"
)
def quote_payment(payload: PaymentQuoteRequest, _: Annotated[UUID, Depends(get_user_id)]) -> dict[str, str | None]:
    return PaymentQuoteApplicationService().quote(**payload.model_dump())


@router.post(
    "/alipay-orders/create",
    response_model=ProviderOrderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建支付宝官方订单",
)
def create_alipay_order(
    payload: ProviderOrderRequest,
    user_id: Annotated[UUID, Depends(get_user_id)],
    session: Annotated[Session, Depends(get_db)],
) -> dict[str, object]:
    return PaymentApplicationService(session).create_alipay_order(user_id, payload.model_dump())


@router.api_route(
    "/alipay-official/notify",
    methods=["GET", "POST"],
    response_class=PlainTextResponse,
    include_in_schema=False,
    summary="处理支付宝回调",
)
async def alipay_notify(request: Request, session: Annotated[Session, Depends(get_db)]) -> PlainTextResponse:
    if (
        request.method != "POST"
        or request.headers.get("content-type", "").split(";", 1)[0].lower() != "application/x-www-form-urlencoded"
    ):
        return PlainTextResponse("failure")
    params = await _alipay_callback_params(request)
    if not params:
        return PlainTextResponse("failure")
    try:
        return PlainTextResponse(
            "success" if PaymentApplicationService(session).settle_alipay_callback(params) else "failure"
        )
    except Exception:
        logger.exception("支付宝回调处理失败")
        return PlainTextResponse("failure")


@router.get("/orders/detail", response_model=OrderStatusResponse, summary="查询充值订单状态")
def get_order(
    order_no: str, user_id: Annotated[UUID, Depends(get_user_id)], session: Annotated[Session, Depends(get_db)]
) -> dict[str, str]:
    return PaymentApplicationService(session).get_order(user_id, order_no)


@router.get("/orders/paid", response_model=PaidRechargeOrderListResponse, summary="分页查询已支付充值订单")
def list_paid_orders(
    user_id: Annotated[UUID, Depends(get_user_id)],
    session: Annotated[Session, Depends(get_db)],
    page: Annotated[int, Query(ge=1, description="从 1 开始的页码")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="单页最大返回 100 条")] = 20,
) -> dict[str, object]:
    return PaymentOrderQueryService(session).list_paid_orders(user_id, page, page_size)


@router.post(
    "/epay-orders/create",
    response_model=ProviderOrderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建易支付充值订单",
)
def create_epay_order(
    payload: ProviderOrderRequest,
    user_id: Annotated[UUID, Depends(get_user_id)],
    session: Annotated[Session, Depends(get_db)],
) -> dict[str, object]:
    return EpayPaymentApplicationService(session).create_order(user_id, payload.model_dump())


@router.api_route(
    "/epay/notify", methods=["GET"], response_class=PlainTextResponse, include_in_schema=False, summary="处理易支付回调"
)
async def epay_notify(request: Request, session: Annotated[Session, Depends(get_db)]) -> PlainTextResponse:
    params = _epay_callback_params(request)
    if not params:
        return PlainTextResponse("fail")
    try:
        return PlainTextResponse(
            "success" if EpayPaymentApplicationService(session).settle_callback(params) else "fail"
        )
    except Exception:
        return PlainTextResponse("fail")


@router.post(
    "/stripe-orders/create",
    response_model=StripeProviderOrderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建 Stripe 美元充值订单",
)
def create_stripe_order(
    payload: ProviderOrderRequest,
    user_id: Annotated[UUID, Depends(get_user_id)],
    session: Annotated[Session, Depends(get_db)],
) -> dict[str, object]:
    return StripePaymentApplicationService(session).create_order(user_id, payload.model_dump())


@router.post("/stripe/notify", include_in_schema=False, summary="处理 Stripe 回调")
async def stripe_notify(request: Request, session: Annotated[Session, Depends(get_db)]) -> Response:
    content_length = request.headers.get("content-length")
    if content_length and (not content_length.isdigit() or int(content_length) > _MAX_STRIPE_BODY_SIZE):
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Webhook 请求过大")
    payload = await request.body()
    if len(payload) > _MAX_STRIPE_BODY_SIZE:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Webhook 请求过大")
    signature = request.headers.get("stripe-signature")
    if not signature:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Webhook 签名缺失")
    StripePaymentApplicationService(session).settle_callback(payload, signature)
    return Response(status_code=status.HTTP_200_OK)


async def _alipay_callback_params(request: Request) -> dict[str, str]:
    content_length = request.headers.get("content-length")
    if content_length and (not content_length.isdigit() or int(content_length) > _MAX_CALLBACK_BODY):
        return {}
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > _MAX_CALLBACK_BODY:
            return {}
        chunks.append(chunk)
    try:
        pairs = parse_qsl(b"".join(chunks).decode("utf-8"), keep_blank_values=True, max_num_fields=_MAX_CALLBACK_FIELDS)
    except (UnicodeDecodeError, ValueError):
        return {}
    if len(pairs) > _MAX_CALLBACK_FIELDS or len({key for key, _ in pairs}) != len(pairs):
        return {}
    return dict(pairs)


def _epay_callback_params(request: Request) -> dict[str, str]:
    query = request.url.query
    if len(query.encode()) > _MAX_CALLBACK_BODY:
        return {}
    try:
        pairs = parse_qsl(query, keep_blank_values=True, max_num_fields=_MAX_CALLBACK_FIELDS)
    except ValueError:
        return {}
    if len(pairs) > _MAX_CALLBACK_FIELDS or len({key for key, _ in pairs}) != len(pairs):
        return {}
    return dict(pairs)
