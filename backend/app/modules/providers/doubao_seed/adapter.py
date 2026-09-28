"""豆包 Seed（火山方舟）Responses Provider 适配器。

适配器把平台文本生成端口映射到火山方舟原生 Responses 接口，按渠道冻结的 ``base_url``（通常为
``https://ark.cn-beijing.volces.com/api/v3``）拼接 ``/responses``，以 ``Authorization: Bearer`` 鉴权；
请求体保持 Ark Responses 原生结构，响应与 SSE 事件原样返回。凭据仅保留在实例内存中。
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
from app.modules.providers.contracts import ProviderError, ProviderProtocolOperation, ProviderUpload
from app.modules.providers.http_support import provider_error_from_status, send_provider_request

RESPONSES_PATH = "/responses"


class DoubaoSeedProvider:
    """把平台文本生成端口映射到火山方舟 Responses 接口。"""

    name = "doubao_seed"

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
        raise ValueError("豆包 Seed Provider 不支持 OpenAI 图片接口")

    def validate_chat_request(self, request_body: dict[str, Any]) -> None:
        raise ValueError("豆包 Seed Provider 仅支持 Responses 接口")

    def validate_response_request(self, request_body: dict[str, Any]) -> None:
        """校验 Ark Responses 请求包含模型名与非空 ``input``。"""

        _require_str_field(request_body, "model")
        if request_body.get("input") in (None, "", [], {}):
            raise ValueError("豆包 Seed 请求必须提供非空 input")

    def protocol_operations(self) -> set[ProviderProtocolOperation]:
        return {ProviderProtocolOperation("ark_responses", "create")}

    def capabilities(self) -> set[str]:
        return {"ark_response_creation", "ark_response_stream"}

    async def generate_image(self, request_body: dict[str, Any], *, timeout: float | None = None) -> dict[str, Any]:
        raise ValueError("豆包 Seed Provider 不支持 OpenAI 图片接口")

    async def edit_image(
        self, request_body: dict[str, Any], uploads: list[ProviderUpload], *, timeout: float | None = None
    ) -> dict[str, Any]:
        raise ValueError("豆包 Seed Provider 不支持 OpenAI 图片接口")

    async def chat(self, request_body: dict[str, Any], *, timeout: float | None = None) -> dict[str, Any]:
        raise ValueError("豆包 Seed Provider 仅支持 Responses 接口")

    async def open_chat_stream(self, request_body: dict[str, Any]) -> tuple[AsyncIterator[bytes], str]:
        raise ValueError("豆包 Seed Provider 仅支持 Responses 接口")

    async def create_response(self, request_body: dict[str, Any], *, timeout: float | None = None) -> dict[str, Any]:
        """调用 Ark Responses 接口并返回原生响应体。"""

        self.validate_response_request(request_body)
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
                self._url(),
                provider_type=self.name,
                headers=self._auth_headers(),
                json=request_body,
                **kwargs,
            )
        except httpx.TimeoutException as exc:
            raise ProviderError("请求超时", code="timeout", retryable=True) from exc
        except httpx.HTTPError as exc:
            raise ProviderError("上游服务不可用", code="network", retryable=True) from exc
        finally:
            await self._close_if_owned()
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

    async def open_response_stream(self, request_body: dict[str, Any]) -> tuple[AsyncIterator[bytes], str]:
        """打开 Ark Responses 流并返回 SSE 字节流和内容类型。"""

        self.validate_response_request(request_body)
        try:
            response = await send_provider_request(
                self._client,
                "POST",
                self._url(),
                provider_type=self.name,
                headers=self._auth_headers(),
                json=request_body,
                stream=True,
            )
            status_error = provider_error_from_status(response)
            if status_error is not None:
                raise status_error
        except Exception:
            if "response" in locals():
                await response.aclose()
            await self._close_if_owned()
            raise
        content_type = response.headers.get("content-type", "text/event-stream")

        async def chunks() -> AsyncIterator[bytes]:
            try:
                async for chunk in response.aiter_bytes():
                    yield chunk
            finally:
                await response.aclose()
                await self._close_if_owned()

        return chunks(), content_type

    def _url(self) -> str:
        if not isinstance(self._base_url, str) or not self._base_url or not self._api_key:
            raise ProviderError("渠道 Provider 未配置凭据", code="unknown_provider", retryable=False)
        return f"{self._base_url}{RESPONSES_PATH}"

    def _auth_headers(self) -> dict[str, str]:
        if not isinstance(self._api_key, str) or not self._api_key:
            raise ProviderError("渠道 Provider 未配置凭据", code="unknown_provider", retryable=False)
        return {"Authorization": f"Bearer {self._api_key}"}

    async def _close_if_owned(self) -> None:
        """仅关闭测试注入传输时创建的独立客户端，不关闭进程共享客户端。"""

        if self._owns_client:
            await self._client.aclose()


def _require_str_field(request_body: dict[str, Any], field: str) -> str:
    value = request_body.get(field)
    if not isinstance(value, str) or not value:
        raise ValidationError(
            f"请求必须提供非空 {field}", code="contract.non_empty_field_required", params={"name": field}
        )
    return value
