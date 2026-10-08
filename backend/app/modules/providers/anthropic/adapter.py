"""Anthropic Messages 原生 Provider 适配器，并兼容 OpenAI Chat / Responses 协议面。

``/v1/messages`` 保持 Anthropic 原生请求与响应；``/v1/chat/completions`` 与 ``/v1/responses`` 走
OpenAI 协议形状。路由在请求体注入平台内部字段 ``ENDPOINT_FIELD`` 标识来源端点，适配器据此选择
原生透传或调用 :mod:`app.modules.providers.anthropic.compat` 完成与 Messages 的互译，并在转发上游前
剥离该字段，因此上游不会收到平台内部字段，客户端也无法通过请求体自行改变端点。

Provider 仅在 ``/v1/messages`` 面上原样转发厂商请求；OpenAI 协议面的互译是本适配器承载的公开兼容
能力，不改变上游 Messages 端点本身的请求编码、成功响应与流式事件。
"""

from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.core.errors import ValidationError
from app.infrastructure.http.client import (
    CONNECT_TIMEOUT_SECONDS,
    POOL_TIMEOUT_SECONDS,
    WRITE_TIMEOUT_SECONDS,
    get_async_http_client,
)
from app.modules.providers.anthropic.compat import (
    ChatStreamTranslator,
    ResponsesStreamTranslator,
    chat_request_to_messages,
    messages_response_to_chat,
    messages_response_to_responses,
    responses_request_to_messages,
)
from app.modules.providers.contracts import ProviderError, ProviderProtocolOperation, ProviderUpload
from app.modules.providers.http_support import provider_error_from_status, send_provider_request

PROVIDER_NAME = "anthropic"

ENDPOINT_FIELD = "_anthropic_endpoint"
"""路由注入的平台内部端点字段，用于区分公开路径对应的调用形状。"""

MESSAGES_ENDPOINT = "messages"
CHAT_COMPLETIONS_ENDPOINT = "chat_completions"
RESPONSES_ENDPOINT = "responses"
_ENDPOINTS = frozenset({MESSAGES_ENDPOINT, CHAT_COMPLETIONS_ENDPOINT, RESPONSES_ENDPOINT})

_MESSAGES_PATH = "/v1/messages"
_ANTHROPIC_VERSION = "2023-06-01"


class AnthropicProvider:
    name = PROVIDER_NAME

    def __init__(
        self,
        base_url: str | None,
        api_key: str | None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/") if isinstance(base_url, str) and base_url else None
        self._api_key = api_key if isinstance(api_key, str) and api_key else None
        self._client = get_async_http_client(transport=transport)
        self._owns_client = transport is not None

    def validate_image_request(self, request_body: dict[str, Any]) -> None:
        raise ValueError("Anthropic Messages Provider 不支持图片生成")

    def validate_chat_request(self, request_body: dict[str, Any]) -> None:
        if _endpoint(request_body) == CHAT_COMPLETIONS_ENDPOINT:
            _require_str_field(request_body, "model")
            _require_messages(request_body)
            return
        _require_str_field(request_body, "model")
        _require_messages(request_body)
        max_tokens = request_body.get("max_tokens")
        if not isinstance(max_tokens, int) or isinstance(max_tokens, bool) or max_tokens <= 0:
            raise ValueError("Anthropic Messages 请求必须提供大于 0 的 max_tokens")

    def validate_response_request(self, request_body: dict[str, Any]) -> None:
        _require_str_field(request_body, "model")
        if request_body.get("input") in (None, "", [], {}):
            raise ValueError("Anthropic Responses 请求必须提供非空 input")

    def protocol_operations(self) -> set[ProviderProtocolOperation]:
        return {
            ProviderProtocolOperation("anthropic_messages", "create"),
            ProviderProtocolOperation("openai_text", "create"),
            ProviderProtocolOperation("openai_response", "create"),
        }

    def capabilities(self) -> set[str]:
        return {"chat_completion", "chat_stream", "response_creation", "response_stream"}

    async def generate_image(self, request_body: dict[str, Any], *, timeout: float | None = None) -> dict[str, Any]:
        raise ValueError("Anthropic Messages Provider 不支持图片生成")

    async def edit_image(
        self, request_body: dict[str, Any], uploads: list[ProviderUpload], *, timeout: float | None = None
    ) -> dict[str, Any]:
        raise ValueError("Anthropic Messages Provider 不支持图片编辑")

    async def chat(self, request_body: dict[str, Any], *, timeout: float | None = None) -> dict[str, Any]:
        self.validate_chat_request(request_body)
        if _endpoint(request_body) == CHAT_COMPLETIONS_ENDPOINT:
            upstream_body = chat_request_to_messages(_strip_endpoint(request_body))
            try:
                payload = await self._request_json(_MESSAGES_PATH, upstream_body, timeout=timeout)
            finally:
                await self._close_if_owned()
            return messages_response_to_chat(payload)
        try:
            return await self._request_json(_MESSAGES_PATH, _strip_endpoint(request_body), timeout=timeout)
        finally:
            await self._close_if_owned()

    async def open_chat_stream(self, request_body: dict[str, Any]) -> tuple[AsyncIterator[bytes], str]:
        self.validate_chat_request(request_body)
        if _endpoint(request_body) == CHAT_COMPLETIONS_ENDPOINT:
            response = await self._send_stream(chat_request_to_messages(_strip_endpoint(request_body)))
            content_type = response.headers.get("content-type", "text/event-stream")
            return self._translated_stream(response, ChatStreamTranslator()), content_type
        response = await self._send_stream(_strip_endpoint(request_body))
        content_type = response.headers.get("content-type", "text/event-stream")

        async def chunks() -> AsyncIterator[bytes]:
            try:
                async for chunk in response.aiter_bytes():
                    yield chunk
            finally:
                await response.aclose()
                await self._close_if_owned()

        return chunks(), content_type

    async def create_response(self, request_body: dict[str, Any], *, timeout: float | None = None) -> dict[str, Any]:
        self.validate_response_request(request_body)
        upstream_body = responses_request_to_messages(_strip_endpoint(request_body))
        try:
            payload = await self._request_json(_MESSAGES_PATH, upstream_body, timeout=timeout)
        finally:
            await self._close_if_owned()
        return messages_response_to_responses(payload)

    async def open_response_stream(self, request_body: dict[str, Any]) -> tuple[AsyncIterator[bytes], str]:
        self.validate_response_request(request_body)
        upstream_body = responses_request_to_messages(_strip_endpoint(request_body))
        response = await self._send_stream(upstream_body)
        content_type = response.headers.get("content-type", "text/event-stream")
        return self._translated_stream(response, ResponsesStreamTranslator()), content_type

    def _translated_stream(
        self, response: httpx.Response, translator: ChatStreamTranslator | ResponsesStreamTranslator
    ) -> AsyncIterator[bytes]:
        """按行解析上游 SSE，逐事件翻译为 OpenAI 形状后转发。"""

        async def chunks() -> AsyncIterator[bytes]:
            try:
                async for line in response.aiter_lines():
                    for chunk in translator.feed_line(line):
                        yield chunk
                for chunk in translator.finish():
                    yield chunk
            finally:
                await response.aclose()
                await self._close_if_owned()

        return chunks()

    async def _request_json(
        self, path: str, request_body: dict[str, Any], *, timeout: float | None = None
    ) -> dict[str, Any]:
        request_kwargs: dict[str, Any] = {}
        if timeout is not None:
            request_kwargs["timeout"] = httpx.Timeout(
                connect=CONNECT_TIMEOUT_SECONDS,
                read=timeout,
                write=WRITE_TIMEOUT_SECONDS,
                pool=POOL_TIMEOUT_SECONDS,
            )
        try:
            response = await send_provider_request(
                self._client,
                "POST",
                self._url(path),
                provider_type=self.name,
                headers=self._auth_headers(),
                json=request_body,
                **request_kwargs,
            )
        except httpx.TimeoutException as exc:
            raise ProviderError("请求超时", code="timeout", retryable=True) from exc
        except httpx.HTTPError as exc:
            raise ProviderError("上游服务不可用", code="network", retryable=True) from exc
        status_error = provider_error_from_status(response)
        if status_error is not None:
            raise status_error
        try:
            payload = response.json()
        except (UnicodeDecodeError, ValueError) as exc:
            raise ProviderError("上游返回非 JSON 响应", code="invalid_response", retryable=True) from exc
        if not isinstance(payload, dict):
            raise ProviderError("上游返回未知响应结构", code="invalid_response", retryable=True)
        return payload

    async def _send_stream(self, request_body: dict[str, Any]) -> httpx.Response:
        try:
            response = await send_provider_request(
                self._client,
                "POST",
                self._url(_MESSAGES_PATH),
                provider_type=self.name,
                headers=self._auth_headers(),
                json=request_body,
                stream=True,
            )
            status_error = provider_error_from_status(response)
            if status_error is not None:
                raise status_error
        except ProviderError:
            if "response" in locals():
                await response.aclose()
            await self._close_if_owned()
            raise
        except httpx.HTTPError as exc:
            await self._close_if_owned()
            raise ProviderError("上游服务不可用", code="network", retryable=True) from exc
        return response

    def _url(self, path: str) -> str:
        if not self._base_url or not self._api_key:
            raise ProviderError("渠道 Provider 未配置凭据", code="unknown_provider", retryable=False)
        return f"{self._base_url}{path}"

    def _auth_headers(self) -> dict[str, str]:
        if not self._api_key:
            raise ProviderError("渠道 Provider 未配置凭据", code="unknown_provider", retryable=False)
        return {
            "x-api-key": self._api_key,
            "anthropic-version": _ANTHROPIC_VERSION,
            "content-type": "application/json",
        }

    async def _close_if_owned(self) -> None:
        if self._owns_client:
            await self._client.aclose()


def _endpoint(request_body: dict[str, Any]) -> str:
    """按路由注入的平台内部字段返回端点形状，缺失时按原生 Messages 处理。"""

    value = request_body.get(ENDPOINT_FIELD)
    if value is None:
        return MESSAGES_ENDPOINT
    if not isinstance(value, str) or value not in _ENDPOINTS:
        raise ValueError("Anthropic 端点类型不合法")
    return value


def _strip_endpoint(request_body: dict[str, Any]) -> dict[str, Any]:
    """剥离平台内部字段，保证上游只收到 Anthropic Messages 原生请求体。"""

    return {key: value for key, value in request_body.items() if key != ENDPOINT_FIELD}


def _require_messages(request_body: dict[str, Any]) -> None:
    messages = request_body.get("messages")
    if not isinstance(messages, list) or not messages:
        raise ValueError("Anthropic Messages 请求必须提供非空 messages 列表")


def _require_str_field(request_body: dict[str, Any], field: str) -> str:
    value = request_body.get(field)
    if not isinstance(value, str) or not value:
        raise ValidationError(
            f"请求必须提供非空 {field}", code="contract.non_empty_field_required", params={"name": field}
        )
    return value
