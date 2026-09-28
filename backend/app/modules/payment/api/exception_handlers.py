"""支付异常 HTTP 映射，集中将应用层安全错误转换为统一接口响应。"""

from app.core.i18n import translate
from app.modules.payment.application.errors import (
    PaymentAmountInvalidError,
    PaymentBusinessError,
    PaymentCallbackProcessingError,
    PaymentCallbackValidationError,
    PaymentDisabledError,
    PaymentOrderNotFoundError,
    PaymentProviderUnavailableError,
)
from app.web.request_context import get_request_id
from app.web.response import response_body
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse


def _payment_error_response(status_code: int, detail: str) -> JSONResponse:
    """构造符合全局响应约定的支付异常响应。"""
    request_id = get_request_id()
    headers = {"X-Request-ID": request_id} if request_id else {}
    return JSONResponse(
        status_code=status_code,
        content=response_body(status_code, translate(detail), None, request_id),
        headers=headers,
    )


def register_payment_exception_handlers(app: FastAPI) -> None:
    """注册支付应用异常到 HTTP 状态码的唯一映射。"""

    @app.exception_handler(PaymentDisabledError)
    async def handle_payment_disabled(_: Request, exc: PaymentDisabledError) -> JSONResponse:
        return _payment_error_response(status.HTTP_403_FORBIDDEN, "支付功能暂未开启")

    @app.exception_handler(PaymentAmountInvalidError)
    async def handle_invalid_payment_amount(_: Request, exc: PaymentAmountInvalidError) -> JSONResponse:
        return _payment_error_response(status.HTTP_400_BAD_REQUEST, "充值金额不在允许范围内")

    @app.exception_handler(PaymentOrderNotFoundError)
    async def handle_payment_order_not_found(_: Request, exc: PaymentOrderNotFoundError) -> JSONResponse:
        return _payment_error_response(status.HTTP_404_NOT_FOUND, "订单不存在")

    @app.exception_handler(PaymentProviderUnavailableError)
    async def handle_payment_provider_unavailable(_: Request, exc: PaymentProviderUnavailableError) -> JSONResponse:
        return _payment_error_response(status.HTTP_502_BAD_GATEWAY, "支付渠道暂时不可用，请稍后重试")

    @app.exception_handler(PaymentCallbackProcessingError)
    async def handle_payment_callback_processing(_: Request, exc: PaymentCallbackProcessingError) -> JSONResponse:
        return _payment_error_response(status.HTTP_503_SERVICE_UNAVAILABLE, "支付服务暂时无法处理")

    @app.exception_handler(PaymentCallbackValidationError)
    @app.exception_handler(PaymentBusinessError)
    async def handle_payment_business_error(_: Request, exc: PaymentBusinessError) -> JSONResponse:
        return _payment_error_response(status.HTTP_400_BAD_REQUEST, "支付请求校验失败")
