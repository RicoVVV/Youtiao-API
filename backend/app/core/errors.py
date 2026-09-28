"""应用层业务异常，统一承载多语言文案所需的稳定错误码与占位符参数。

约定：
- ``message`` 为中文原文，用于中文响应与内部日志，保持既有断言语义不变；
- ``code`` 为稳定业务码，``params`` 为译文占位符参数；
- 两者同时提供时，响应出口按目标语言重建文案，使同一处 ``raise`` 无需为多语言分支。
"""

from collections.abc import Mapping
from typing import Any


class ApplicationError(Exception):
    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        params: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.params: dict[str, Any] = dict(params) if params else {}


class AuthenticationError(ApplicationError):
    pass


class ConflictError(ApplicationError):
    pass


class NotFoundError(ApplicationError):
    pass


class ValidationError(ApplicationError, ValueError):
    pass


class _UpstreamError(ApplicationError):
    def __init__(
        self,
        message: str,
        *,
        upstream_code: str | None = None,
        upstream_message: str | None = None,
        code: str | None = None,
        params: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message, code=code, params=params)
        self.upstream_code = upstream_code
        self.upstream_message = upstream_message


class UpstreamTimeoutError(_UpstreamError):
    pass


class UpstreamUnavailableError(_UpstreamError):
    pass


class PaymentRequiredError(ApplicationError):
    pass


class RateLimitExceededError(ApplicationError):
    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("请求过于频繁，请稍后重试")
        self.retry_after_seconds = retry_after_seconds


class AuthenticationRateLimitUnavailableError(ApplicationError):
    pass


def error_context(exc: Exception) -> dict[str, Any]:
    """返回内层异常的多语言上下文，供包装点原样透传给外层业务异常。

    应用层多处以 ``except ValueError`` 把内层校验失败包装成对外业务异常；
    若包装时丢弃 ``code`` 与 ``params``，译文会退化为中文原文。
    用法：``raise ValidationError(str(exc), **error_context(exc)) from exc``。
    """

    if isinstance(exc, ApplicationError):
        return {"code": exc.code, "params": exc.params}
    return {}
