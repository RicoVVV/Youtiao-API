"""FastAPI 全局异常映射，隔离内部异常与客户端响应。"""

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import get_settings
from app.core.errors import (
    ApplicationError,
    AuthenticationError,
    AuthenticationProviderUnavailableError,
    AuthenticationRateLimitUnavailableError,
    ConflictError,
    NotFoundError,
    PaymentRequiredError,
    RateLimitExceededError,
    UpstreamTimeoutError,
    UpstreamUnavailableError,
    ValidationError,
)
from app.core.i18n import translate, translate_error
from app.web.protocol_scope import (
    is_anthropic_protocol_path,
    is_dashscope_protocol_path,
    is_gemini_protocol_path,
    is_public_protocol_path,
)
from app.web.request_context import get_request_id
from app.web.response import response_body

logger = logging.getLogger(__name__)

_PROTOCOL_LOCALE = "en"
"""公开协议面统一使用英文。协议错误体对 SDK 客户端必须稳定，不随请求语言变化。"""


def _response_headers(headers: dict[str, str] | None = None) -> dict[str, str]:
    """构造携带当前请求关联标识的安全响应头。"""

    request_id = get_request_id()
    response_headers = dict(headers or {})
    if request_id:
        response_headers["X-Request-ID"] = request_id
    return response_headers


def _is_anthropic_protocol_request(request: Request) -> bool:
    return is_anthropic_protocol_path(request.url.path)


def _is_gemini_protocol_request(request: Request) -> bool:
    return is_gemini_protocol_path(request.url.path)


def _is_dashscope_protocol_request(request: Request) -> bool:
    return is_dashscope_protocol_path(request.url.path)


def _is_public_protocol_request(request: Request) -> bool:
    return is_public_protocol_path(request.url.path)


_ANTHROPIC_ERROR_TYPES = {
    "authentication_error": "authentication_error",
    "permission_error": "permission_error",
    "invalid_request_error": "invalid_request_error",
    "rate_limit_error": "rate_limit_error",
    "server_error": "api_error",
}

_DASHSCOPE_ERROR_CODES = {
    401: "InvalidApiKey",
    402: "Arrearage",
    403: "AccessDenied",
    404: "ModelNotExist",
    409: "InvalidParameter",
    422: "InvalidParameter",
    429: "Throttling",
    500: "InternalError",
    502: "InternalError",
    503: "InternalError",
    504: "RequestTimeout",
}


def _anthropic_error_response(*, status_code: int, message: str, error_type: str, headers=None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"type": "error", "error": {"type": error_type, "message": message}},
        headers=_response_headers(headers),
    )


def _dashscope_error_response(*, status_code: int, message: str, headers=None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "code": _DASHSCOPE_ERROR_CODES.get(status_code, "UnknownError"),
            "message": message,
            "request_id": get_request_id(),
        },
        headers=_response_headers(headers),
    )


def _gemini_error_response(*, status_code: int, message: str, status: str, headers=None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": status_code, "message": message, "status": status}},
        headers=_response_headers(headers),
    )


def _protocol_error_response(
    request: Request,
    *,
    status_code: int,
    message: str,
    error_type: str,
    param: str | None = None,
    code: str | None = None,
    headers=None,
) -> JSONResponse:
    if _is_anthropic_protocol_request(request):
        return _anthropic_error_response(
            status_code=status_code,
            message=message,
            error_type=_ANTHROPIC_ERROR_TYPES.get(error_type, "invalid_request_error"),
            headers=headers,
        )
    if _is_dashscope_protocol_request(request):
        return _dashscope_error_response(
            status_code=status_code,
            message=message,
            headers=headers,
        )
    if _is_gemini_protocol_request(request):
        return _gemini_error_response(status_code=status_code, message=message, status=error_type, headers=headers)
    return _openai_error_response(
        status_code=status_code, message=message, error_type=error_type, param=param, code=code, headers=headers
    )


def _openai_not_found_detail(request: Request) -> tuple[str, str]:
    """按资源路径返回 OpenAI 风格 404 文案与错误码，避免图片/文本误报视频错误。"""

    if request.url.path.startswith("/v1/videos"):
        return "Video not found", "video_not_found"
    return "Resource not found", "not_found"


def _openai_error_response(
    *, status_code: int, message: str, error_type: str, param: str | None = None, code: str | None = None, headers=None
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"message": message, "type": error_type, "param": param, "code": code}},
        headers=_response_headers(headers),
    )


def _upstream_error_detail(
    exc: UpstreamTimeoutError | UpstreamUnavailableError, fallback_message: str, fallback_code: str
) -> tuple[str, str]:
    message = exc.upstream_message or fallback_message
    code = exc.upstream_code or fallback_code
    return message, code


def register_exception_handlers(app: FastAPI) -> None:
    """注册全局 HTTP、参数校验和未知异常处理器。"""

    @app.exception_handler(HTTPException)
    async def handle_http_exception(request: Request, exc: HTTPException) -> JSONResponse:
        if _is_public_protocol_request(request):
            error_type = "authentication_error" if exc.status_code == 401 else "permission_error"
            return _protocol_error_response(
                request,
                status_code=exc.status_code,
                message=translate(str(exc.detail), _PROTOCOL_LOCALE),
                error_type=error_type,
                code="invalid_api_key" if exc.status_code == 401 else None,
                headers=exc.headers,
            )
        return JSONResponse(
            status_code=exc.status_code,
            content=response_body(exc.status_code, translate(str(exc.detail)), None, get_request_id()),
            headers=_response_headers(exc.headers),
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_starlette_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        if _is_public_protocol_request(request):
            return _protocol_error_response(
                request,
                status_code=exc.status_code,
                message=translate(str(exc.detail), _PROTOCOL_LOCALE),
                error_type="invalid_request_error",
                code=_openai_not_found_detail(request)[1] if exc.status_code == 404 else None,
                headers=exc.headers,
            )
        return JSONResponse(
            status_code=exc.status_code,
            content=response_body(exc.status_code, translate(str(exc.detail)), None, get_request_id()),
            headers=_response_headers(exc.headers),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_exception(request: Request, exc: RequestValidationError) -> JSONResponse:
        if _is_public_protocol_request(request):
            errors = exc.errors()
            location = errors[0].get("loc", []) if errors else []
            param = location[-1] if location and isinstance(location[-1], str) else None
            return _protocol_error_response(
                request,
                status_code=422,
                message="Invalid request parameters",
                error_type="invalid_request_error",
                param=param,
                code="invalid_request_error",
            )
        return JSONResponse(
            status_code=422,
            content=response_body(422, translate("请求参数校验失败"), exc.errors(), get_request_id()),
            headers=_response_headers(),
        )

    @app.exception_handler(NotFoundError)
    async def handle_not_found_error(request: Request, exc: NotFoundError) -> JSONResponse:
        if _is_public_protocol_request(request):
            message, code = _openai_not_found_detail(request)
            return _protocol_error_response(
                request,
                status_code=404,
                message=message,
                error_type="invalid_request_error",
                code=code,
            )
        return JSONResponse(
            status_code=404,
            content=response_body(404, translate_error(exc), None, get_request_id()),
            headers=_response_headers(),
        )

    @app.exception_handler(AuthenticationError)
    async def handle_authentication_error(request: Request, exc: AuthenticationError) -> JSONResponse:
        if _is_public_protocol_request(request):
            return _protocol_error_response(
                request,
                status_code=401,
                message="Invalid API key",
                error_type="authentication_error",
                code="invalid_api_key",
            )
        response = JSONResponse(
            status_code=401,
            content=response_body(401, translate_error(exc), None, get_request_id()),
            headers=_response_headers(),
        )
        settings = get_settings()
        response.delete_cookie("refresh_token", path="/api/auth", domain=settings.auth_cookie_domain)
        return response

    @app.exception_handler(RateLimitExceededError)
    async def handle_rate_limit_error(request: Request, exc: RateLimitExceededError) -> JSONResponse:
        headers = {"Retry-After": str(exc.retry_after_seconds)}
        if _is_public_protocol_request(request):
            return _protocol_error_response(
                request,
                status_code=429,
                message="Rate limit exceeded",
                error_type="rate_limit_error",
                code="rate_limit_exceeded",
                headers=headers,
            )
        return JSONResponse(
            status_code=429,
            content=response_body(429, translate_error(exc), None, get_request_id()),
            headers=_response_headers(headers),
        )

    @app.exception_handler(AuthenticationProviderUnavailableError)
    @app.exception_handler(AuthenticationRateLimitUnavailableError)
    async def handle_auth_rate_limit_unavailable(
        request: Request, exc: AuthenticationRateLimitUnavailableError | AuthenticationProviderUnavailableError
    ) -> JSONResponse:
        if _is_public_protocol_request(request):
            return _protocol_error_response(
                request,
                status_code=503,
                message="Authentication service temporarily unavailable",
                error_type="server_error",
                code="authentication_unavailable",
            )
        return JSONResponse(
            status_code=503,
            content=response_body(503, translate_error(exc), None, get_request_id()),
            headers=_response_headers(),
        )

    @app.exception_handler(ConflictError)
    async def handle_conflict_error(request: Request, exc: ConflictError) -> JSONResponse:
        if _is_public_protocol_request(request):
            return _protocol_error_response(
                request,
                status_code=409,
                message="Request conflicts with an existing resource",
                error_type="invalid_request_error",
                code="conflict",
            )
        return JSONResponse(
            status_code=409,
            content=response_body(409, translate_error(exc), None, get_request_id()),
            headers=_response_headers(),
        )

    @app.exception_handler(ValidationError)
    @app.exception_handler(ApplicationError)
    async def handle_application_error(request: Request, exc: ApplicationError) -> JSONResponse:
        if _is_public_protocol_request(request):
            return _protocol_error_response(
                request,
                status_code=422,
                message=translate_error(exc, _PROTOCOL_LOCALE),
                error_type="invalid_request_error",
                code="invalid_request_error",
            )
        return JSONResponse(
            status_code=422,
            content=response_body(422, translate_error(exc), None, get_request_id()),
            headers=_response_headers(),
        )

    @app.exception_handler(PaymentRequiredError)
    async def handle_payment_required_error(request: Request, exc: PaymentRequiredError) -> JSONResponse:
        if _is_public_protocol_request(request):
            return _protocol_error_response(
                request,
                status_code=402,
                message="Insufficient balance",
                error_type="invalid_request_error",
                code="insufficient_balance",
            )
        return JSONResponse(
            status_code=402,
            content=response_body(402, translate_error(exc), None, get_request_id()),
            headers=_response_headers(),
        )

    @app.exception_handler(UpstreamTimeoutError)
    async def handle_upstream_timeout(request: Request, exc: UpstreamTimeoutError) -> JSONResponse:
        if _is_public_protocol_request(request):
            message, code = _upstream_error_detail(exc, "Upstream service timed out", "upstream_timeout")
            return _protocol_error_response(
                request,
                status_code=504,
                message=message,
                error_type="server_error",
                code=code,
            )
        return JSONResponse(
            status_code=504,
            content=response_body(504, translate_error(exc), None, get_request_id()),
            headers=_response_headers(),
        )

    @app.exception_handler(UpstreamUnavailableError)
    async def handle_upstream_unavailable(request: Request, exc: UpstreamUnavailableError) -> JSONResponse:
        if _is_public_protocol_request(request):
            message, code = _upstream_error_detail(exc, "Upstream service unavailable", "upstream_unavailable")
            return _protocol_error_response(
                request,
                status_code=502,
                message=message,
                error_type="server_error",
                code=code,
            )
        return JSONResponse(
            status_code=502,
            content=response_body(502, translate_error(exc), None, get_request_id()),
            headers=_response_headers(),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_exception(request: Request, _: Exception) -> JSONResponse:
        logger.exception(
            "HTTP 请求发生未处理异常 request_id=%s method=%s path=%s",
            get_request_id(),
            request.method,
            request.url.path,
        )
        if _is_public_protocol_request(request):
            return _protocol_error_response(
                request,
                status_code=500,
                message="Internal server error",
                error_type="server_error",
                code="internal_error",
            )
        return JSONResponse(
            status_code=500,
            content=response_body(500, translate("服务暂时不可用"), None, get_request_id()),
            headers=_response_headers(),
        )
