"""Gemini 原生文本 Provider 适配器。"""

from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import quote

import httpx

from app.core.errors import ValidationError
from app.infrastructure.http.client import (
    CONNECT_TIMEOUT_SECONDS,
    POOL_TIMEOUT_SECONDS,
    WRITE_TIMEOUT_SECONDS,
    get_async_http_client,
)
from app.modules.providers.contracts import ProviderError, ProviderProtocolOperation, ProviderUpload
from app.modules.providers.http_support import provider_error_from_status, send_provider_request


class GeminiProvider:
    """将平台文本生成端口映射到 Gemini 原生内容生成接口。"""

    name = "gemini"

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
        """校验 Gemini 图像请求包含字符串模型名和非空 contents 列表。"""

        _require_str_field(request_body, "model")
        contents = request_body.get("contents")
        if not isinstance(contents, list) or not contents:
            raise ValueError("Gemini 图像请求必须提供非空 contents 列表")

    def validate_response_request(self, request_body: dict[str, Any]) -> None:
        raise ValueError("Gemini Provider 不支持 OpenAI Responses API")

    def validate_chat_request(self, request_body: dict[str, Any]) -> None:
        _require_str_field(request_body, "model")
        contents = request_body.get("contents")
        if not isinstance(contents, list) or not contents:
            raise ValueError("Gemini 请求必须提供非空 contents 列表")

    def protocol_operations(self) -> set[ProviderProtocolOperation]:
        return {
            ProviderProtocolOperation("gemini_text", "generate"),
            ProviderProtocolOperation("gemini_text", "stream"),
        }

    def capabilities(self) -> set[str]:
        return {"gemini_generate_content", "gemini_stream", "gemini_image_generation"}

    async def generate_image(self, request_body: dict[str, Any], *, timeout: float | None = None) -> dict[str, Any]:
        """调用 Gemini generateContent 生成图片，编辑输入以内联图片块随 contents 提交。"""

        self.validate_image_request(request_body)
        try:
            return await self._request_json(
                self._path(request_body, "generateContent"), self._body(request_body), timeout=timeout
            )
        finally:
            await self._close_if_owned()

    async def edit_image(
        self, request_body: dict[str, Any], uploads: list[ProviderUpload], *, timeout: float | None = None
    ) -> dict[str, Any]:
        """Gemini 图像编辑通过 contents 内联图片完成，不接受 multipart 上传。"""

        raise ValueError("Gemini Provider 不支持 multipart 图片编辑")

    async def create_response(self, request_body: dict[str, Any], *, timeout: float | None = None) -> dict[str, Any]:
        raise ValueError("Gemini Provider 不支持 OpenAI Responses API")

    async def chat(self, request_body: dict[str, Any], *, timeout: float | None = None) -> dict[str, Any]:
        self.validate_chat_request(request_body)
        try:
            return await self._request_json(
                self._path(request_body, "generateContent"), self._body(request_body), timeout=timeout
            )
        finally:
            await self._close_if_owned()

    async def open_chat_stream(self, request_body: dict[str, Any]) -> tuple[AsyncIterator[bytes], str]:
        self.validate_chat_request(request_body)
        response = await self._send_stream(
            self._path(request_body, "streamGenerateContent?alt=sse"), self._body(request_body)
        )
        content_type = response.headers.get("content-type", "text/event-stream")

        async def chunks() -> AsyncIterator[bytes]:
            try:
                async for chunk in response.aiter_bytes():
                    yield chunk
            finally:
                await response.aclose()
                await self._close_if_owned()

        return chunks(), content_type

    async def open_response_stream(self, request_body: dict[str, Any]) -> tuple[AsyncIterator[bytes], str]:
        raise ValueError("Gemini Provider 不支持 OpenAI Responses API")

    async def _request_json(self, path: str, body: dict[str, Any], *, timeout: float | None = None) -> dict[str, Any]:
        kwargs: dict[str, Any] = {}
        if timeout is not None:
            kwargs["timeout"] = httpx.Timeout(
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
                json=body,
                **kwargs,
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

    async def _send_stream(self, path: str, body: dict[str, Any]) -> httpx.Response:
        try:
            response = await send_provider_request(
                self._client,
                "POST",
                self._url(path),
                provider_type=self.name,
                headers=self._auth_headers(),
                json=body,
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

    @staticmethod
    def _body(request_body: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in request_body.items() if key != "model"}

    @staticmethod
    def _path(request_body: dict[str, Any], action: str) -> str:
        model = _require_str_field(request_body, "model")
        normalized = model.removeprefix("models/")
        return f"/v1beta/models/{quote(normalized, safe='-._')}:{action}"

    def _url(self, path: str) -> str:
        if not self._base_url or not self._api_key:
            raise ProviderError("渠道 Provider 未配置凭据", code="unknown_provider", retryable=False)
        return f"{self._base_url}{path}"

    def _auth_headers(self) -> dict[str, str]:
        if not self._api_key:
            raise ProviderError("渠道 Provider 未配置凭据", code="unknown_provider", retryable=False)
        return {"x-goog-api-key": self._api_key}

    async def _close_if_owned(self) -> None:
        if self._owns_client:
            await self._client.aclose()


def _require_str_field(request_body: dict[str, Any], field: str) -> str:
    value = request_body.get(field)
    if not isinstance(value, str) or not value:
        raise ValidationError(
            f"请求必须提供非空 {field}", code="contract.non_empty_field_required", params={"name": field}
        )
    return value
