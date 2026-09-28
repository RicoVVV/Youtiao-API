"""HTTP 请求关联标识的生成、传播和访问日志边界。"""

import json
import logging
import re
import time
from contextvars import ContextVar
from uuid import uuid4

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.i18n import (
    ACCEPT_LANGUAGE_HEADER,
    LOCALE_HEADER,
    reset_locale,
    resolve_locale,
    set_locale,
    translate,
)
from app.core.logging import bind_request_id, reset_request_id
from app.web.protocol_scope import is_public_protocol_path
from app.web.response import response_body

_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
logger = logging.getLogger(__name__)


def get_request_id() -> str | None:
    """返回当前请求的关联标识，非 HTTP 上下文时返回空值。"""

    return _request_id.get()


def resolve_request_id(value: str | None) -> str:
    """保留合法客户端关联标识，其他输入生成新的 UUID。"""

    if value is not None and _REQUEST_ID_PATTERN.fullmatch(value):
        return value
    return str(uuid4())


class RequestContextMiddleware(BaseHTTPMiddleware):
    """为每个 HTTP 请求绑定关联标识、记录访问摘要并回传响应头。"""

    async def dispatch(self, request: Request, call_next):
        """在请求生命周期内绑定关联标识，并确保响应包含该标识。"""

        request_id = resolve_request_id(request.headers.get("X-Request-ID"))
        request.state.request_id = request_id
        token = _request_id.set(request_id)
        log_token = bind_request_id(request_id)
        locale_token = set_locale(
            resolve_locale(request.headers.get(LOCALE_HEADER), request.headers.get(ACCEPT_LANGUAGE_HEADER))
        )
        started_at = time.perf_counter()
        response = None
        try:
            response = await call_next(request)
            response = await self._wrap_json_response(request, response, request_id)
            return response
        except Exception:
            logger.exception(
                "HTTP 请求发生未处理异常 request_id=%s",
                request_id,
                extra={"request_id": request_id, "method": request.method, "path": request.url.path},
            )
            response = JSONResponse(
                status_code=500,
                content=(
                    {
                        "error": {
                            "message": "Internal server error",
                            "type": "server_error",
                            "param": None,
                            "code": "internal_error",
                        }
                    }
                    if is_public_protocol_path(request.url.path)
                    else response_body(500, translate("服务暂时不可用"), None, request_id)
                ),
            )
            return response
        finally:
            status_code = response.status_code if response is not None else 500
            response_time_ms = round((time.perf_counter() - started_at) * 1000, 2)
            route = request.scope.get("route")
            path = getattr(route, "path", request.url.path)
            if status_code >= 400:
                log_method = logger.error if status_code >= 500 else logger.warning
                reason = self._response_message(response)
                log_method(
                    "HTTP 请求失败 status_code=%s reason=%s",
                    status_code,
                    reason,
                    extra={
                        "request_id": request_id,
                        "method": request.method,
                        "route": path,
                        "status_code": status_code,
                        "reason": reason,
                        "duration_ms": response_time_ms,
                    },
                )
            if response is not None:
                response.headers["X-Request-ID"] = request_id
            reset_request_id(log_token)
            _request_id.reset(token)
            reset_locale(locale_token)

    async def _wrap_json_response(self, request: Request, response, request_id: str):
        """为非探针 JSON 响应添加统一信封，文件流和文档等非 JSON 响应保持原样。"""

        if request.url.path in {"/api/health", "/api/openapi.json"} or "application/json" not in response.headers.get(
            "content-type", ""
        ):
            return response
        body = b"".join([chunk async for chunk in response.body_iterator])
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return response
        headers = {key: value for key, value in response.headers.items() if key.lower() != "content-length"}
        if is_public_protocol_path(request.url.path):
            return JSONResponse(status_code=response.status_code, content=data, headers=headers)
        if isinstance(data, dict) and {"code", "message", "data", "request_id"} <= data.keys():
            return JSONResponse(status_code=response.status_code, content=data, headers=headers)
        return JSONResponse(
            status_code=response.status_code,
            content=response_body(response.status_code, translate("操作成功"), data, request_id),
            headers=headers,
        )

    @staticmethod
    def _response_message(response) -> str:
        """从统一 JSON 错误响应中提取安全的失败原因。"""

        if response is None or "application/json" not in response.headers.get("content-type", ""):
            return "服务暂时不可用"
        try:
            data = json.loads(response.body.decode())
        except (AttributeError, UnicodeDecodeError, json.JSONDecodeError):
            return "服务暂时不可用"
        message = data.get("message") if isinstance(data, dict) else None
        if message is None and isinstance(data, dict) and isinstance(data.get("error"), dict):
            message = data["error"].get("message")
        return message if isinstance(message, str) else "服务暂时不可用"
