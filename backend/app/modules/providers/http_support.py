"""Provider HTTP 适配器共享的上游请求入口、日志脱敏与错误映射工具。

适配器访问上游必须经由 ``send_provider_request``：该入口统一打印脱敏后的请求体、响应体以及超时/网络
失败日志，新增 Provider 只需把上游调用改走该入口即可获得一致可观测性；流式响应体由调用方读取后通过
``log_provider_response`` 补全结果日志。本模块不保存渠道地址、认证信息或具体厂商字段语义，各适配器负责
业务字段解析与异常映射。请求体与响应体在写入日志或附加到 ``ProviderError`` 前必须脱敏：认证类字段替换
为 ``***``，内联 base64 媒体替换为长度摘要，二进制内容与文件上传替换为体积摘要，避免密钥和二进制被完整输出。
"""

import logging
import time
from typing import Any

import httpx

from app.modules.providers.contracts import ProviderError

logger = logging.getLogger(__name__)

_SENSITIVE_FIELDS = frozenset(
    {
        "access_token",
        "refresh_token",
        "id_token",
        "authorization",
        "api_key",
        "apikey",
        "secret",
        "client_secret",
        "password",
    }
)
_BASE64_FIELDS = frozenset({"b64_json", "b64", "base64"})
_BASE64_PAYLOAD_FIELDS = frozenset({"data", "image_base64", "audio_base64", "video_base64"})
_BASE64_PAYLOAD_MIN_LENGTH = 64
_BASE64_ALPHABET = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=_-")
_TEXT_MEDIA_TYPES = ("text/", "application/json", "application/xml", "application/xhtml+xml", "application/javascript")
_TEXT_MEDIA_TYPE_SUFFIXES = ("+json", "+xml")


def _media_type(response: httpx.Response) -> str:
    """取响应 Content-Type 的主类型，去掉 charset 等参数。"""

    return response.headers.get("content-type", "").split(";", 1)[0].strip().lower()


def _is_text_response(response: httpx.Response) -> bool:
    """判断响应体能否安全按文本输出：优先看 Content-Type，缺失时以内容前缀兜底。"""

    media_type = _media_type(response)
    if media_type.startswith(_TEXT_MEDIA_TYPES) or media_type.endswith(_TEXT_MEDIA_TYPE_SUFFIXES):
        return True
    if media_type:
        return False
    return b"\x00" not in response.content[:1024]


def _binary_summary(response: httpx.Response) -> str:
    """生成二进制响应体的摘要，避免把媒体字节写入日志或错误快照。"""

    return f"[binary {_media_type(response) or 'unknown'} {len(response.content)} bytes]"


def _sanitize_text(value: str) -> str:
    """把内联 base64 的 data URL 替换为长度摘要，保留其余文本。"""

    if value.startswith("data:") and ";base64," in value:
        header, _, payload = value.partition(";base64,")
        return f"[base64 {header[len('data:') :]} {len(payload)} chars]"
    return value


def _looks_like_base64(value: str) -> bool:
    """判断字段值是否像内联 base64 载荷：足够长、无空白且只含 base64 字符集。"""

    if len(value) < _BASE64_PAYLOAD_MIN_LENGTH or value.strip() != value:
        return False
    return all(char in _BASE64_ALPHABET for char in value)


def _sanitize_value(value: Any) -> Any:
    """递归脱敏上游请求或响应，处理字典、列表、元组、字符串与二进制内容。"""

    if isinstance(value, dict):
        return {key: _sanitize_field(key, item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, str):
        return _sanitize_text(value)
    if isinstance(value, bytes | bytearray):
        return f"[binary {len(value)} bytes]"
    return value


def _sanitize_field(key: Any, value: Any) -> Any:
    """按字段名脱敏：认证字段打码，内联 base64 字段与 base64 载荷替换为长度摘要。"""

    name = str(key).lower()
    if name in _SENSITIVE_FIELDS:
        return "***"
    if isinstance(value, str):
        if name in _BASE64_FIELDS:
            return f"[base64 {len(value)} chars]"
        if name in _BASE64_PAYLOAD_FIELDS and _looks_like_base64(value):
            return f"[base64 {len(value)} chars]"
    return _sanitize_value(value)


def _sanitized_response(response: httpx.Response) -> Any:
    """解析并脱敏上游响应体；二进制响应只保留摘要。"""

    if not _is_text_response(response):
        return {"binary": _binary_summary(response)}
    return _sanitize_value(response_json(response))


def response_json(response: httpx.Response) -> Any:
    """解析上游响应 JSON，无法解析时回退为原始文本。"""

    try:
        return response.json()
    except (UnicodeDecodeError, ValueError):
        return response.text


def response_body_for_log(response: httpx.Response) -> Any:
    """返回脱敏后的上游响应体，供结构化日志记录。"""

    return _sanitized_response(response)


def response_payload(response: httpx.Response) -> dict[str, Any]:
    """提取脱敏后的上游响应体，供任务错误快照和排障使用。"""

    value = _sanitized_response(response)
    return value if isinstance(value, dict) else {"body": value}


def _request_body_for_log(*, json_body: Any = None, form: Any = None, files: Any = None) -> dict[str, Any]:
    """聚合脱敏后的上游请求体：JSON 体、multipart 表单字段与文件上传分别成键。"""

    parts = {"json": json_body, "form": form, "files": files}
    return {name: _sanitize_value(value) for name, value in parts.items() if value is not None}


def _timeout_seconds(value: Any) -> float | None:
    """从 httpx 超时配置中提取读取超时秒数，供日志记录。"""

    if isinstance(value, httpx.Timeout):
        return value.read
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return None


async def send_provider_request(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    provider_type: str,
    stream: bool = False,
    **kwargs: Any,
) -> httpx.Response:
    """发送上游请求并打印脱敏后的请求体、响应体或超时/网络失败日志。

    参数：client 为共享异步客户端；method 与 url 为上游请求目标；provider_type 写入日志用于区分厂商；
    stream 为真时只记录请求侧与上游状态，响应体由调用方读取后经 ``log_provider_response`` 记录；
    kwargs 原样透传给 ``httpx.AsyncClient.build_request``，请求头不写入日志以免泄漏渠道凭据。
    返回值：上游响应对象，失败时原样抛出 httpx 异常由适配器映射为 ``ProviderError``。
    副作用：写入 INFO/WARNING 结构化日志。
    """

    started_at = time.perf_counter()
    target = httpx.URL(url)
    path = target.path
    # 上游主机不进请求头（避免凭据泄漏），但排障必须知道实际打到哪个地址，因此随日志输出
    host = target.host
    request_body = _request_body_for_log(
        json_body=kwargs.get("json"), form=kwargs.get("data"), files=kwargs.get("files")
    )
    request = client.build_request(method, url, **kwargs)
    try:
        response = await client.send(request, stream=stream)
    except httpx.TimeoutException as exc:
        logger.warning(
            "Provider 请求超时",
            extra={
                "provider_type": provider_type,
                "method": method,
                "host": host,
                "path": path,
                "request_body": request_body,
                "timeout_seconds": _timeout_seconds(kwargs.get("timeout")),
                "error_type": type(exc).__name__,
                "error": str(exc),
                "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
            },
        )
        raise
    except httpx.HTTPError as exc:
        # 传输层失败拿不到响应，只能把异常类型与原因写进日志，否则排障时看不出上游为何未响应
        logger.warning(
            "Provider 请求网络失败",
            extra={
                "provider_type": provider_type,
                "method": method,
                "host": host,
                "path": path,
                "request_body": request_body,
                "error_type": type(exc).__name__,
                "error": str(exc),
                "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
            },
        )
        raise
    extra: dict[str, Any] = {
        "provider_type": provider_type,
        "method": method,
        "host": host,
        "path": path,
        "status_code": response.status_code,
        "request_body": request_body,
        "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
    }
    if stream:
        logger.info("Provider 请求已发出", extra=extra)
    else:
        extra["response_body"] = response_body_for_log(response)
        logger.info("Provider 请求完成", extra=extra)
    return response


def log_provider_response(response: httpx.Response, *, provider_type: str, method: str, url: str) -> None:
    """打印流式响应读取完成后的上游状态与脱敏响应体。

    流式请求由 ``send_provider_request`` 记录请求侧，调用方读取完媒体内容后调用本函数补全结果日志。
    """

    logger.info(
        "Provider 请求完成",
        extra={
            "provider_type": provider_type,
            "method": method,
            "path": httpx.URL(url).path,
            "status_code": response.status_code,
            "response_body": response_body_for_log(response),
        },
    )


def _error_message(payload: dict[str, Any], fallback: str) -> str:
    error = payload.get("error")
    candidates = (
        error.get("message") if isinstance(error, dict) else None,
        payload.get("message"),
        payload.get("body"),
    )
    for candidate in candidates:
        if isinstance(candidate, str) and (message := candidate.strip()):
            return message
    return fallback


def provider_error_from_response(response: httpx.Response) -> ProviderError:
    """把上游业务错误响应映射为不可重试的 ``ProviderError``。"""

    payload = response_payload(response)
    error = payload.get("error") if isinstance(payload.get("error"), dict) else None
    code = error.get("code") if isinstance(error, dict) else None
    message = _error_message(payload, "上游请求被拒绝")
    if code == "insufficient_balance":
        return ProviderError(message, code=code, retryable=False, response_body=payload)
    return ProviderError(message, code=str(code or response.status_code), retryable=False, response_body=payload)


def provider_error_from_status(response: httpx.Response) -> ProviderError | None:
    """按 HTTP 状态映射可重试或业务错误；成功状态返回 ``None``。"""

    if response.status_code == 429 or response.status_code >= 500:
        payload = response_payload(response)
        error = payload.get("error") if isinstance(payload.get("error"), dict) else None
        code = error.get("code") if isinstance(error, dict) else None
        return ProviderError(
            _error_message(payload, "上游服务暂不可用"),
            code=str(code or response.status_code),
            retryable=True,
            response_body=payload,
        )
    if response.is_error:
        return provider_error_from_response(response)
    return None
