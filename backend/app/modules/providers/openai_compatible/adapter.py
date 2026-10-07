"""OpenAI 兼容同步生成 Provider 适配器，隔离图片与文本上游请求和错误契约。

本适配器把平台图片生成、图片编辑和文本补全能力映射到标准 OpenAI 兼容 HTTP 接口，直接透传上游
响应体；认证信息仅保留在渠道实例内存中，不写入日志或快照。
"""

import json
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
from app.modules.providers.contracts import (
    CreateVideoCommand,
    ProviderError,
    ProviderProtocolOperation,
    ProviderSubmission,
    ProviderTaskSnapshot,
    ProviderTaskStatus,
    ProviderUpload,
)
from app.modules.providers.http_support import (
    log_provider_response,
    provider_error_from_status,
    send_provider_request,
)

_IMAGE_GENERATIONS_PATH = "/v1/images/generations"
_IMAGE_EDITS_PATH = "/v1/images/edits"
_CHAT_COMPLETIONS_PATH = "/v1/chat/completions"
_RESPONSES_PATH = "/v1/responses"
_VIDEOS_PATH = "/v1/videos"


def _form_value(value: Any) -> str:
    """把 multipart 字段值编码为上游可接受的字符串。"""

    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return value
    if isinstance(value, int | float):
        return str(value)
    return json.dumps(value, ensure_ascii=False)


class OpenAICompatibleProvider:
    """把同步生成端口映射为标准 OpenAI 兼容 HTTP 接口。"""

    name = "openai_compatible"
    delivers_external_result = False

    def __init__(
        self,
        base_url: str | None,
        api_key: str | None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """使用冻结渠道配置构造客户端，并允许无凭据原型用于发布校验。

        参数：base_url 与 api_key 来自冻结渠道配置，原型校验时可为空；transport 仅用于测试替换传输。
        返回值：无。
        副作用：Provider 密钥仅保留在进程内存中。
        """

        self._base_url = base_url.rstrip("/") if isinstance(base_url, str) and base_url else None
        self._api_key = api_key if isinstance(api_key, str) and api_key else None
        self._client = get_async_http_client(transport=transport)
        self._owns_client = transport is not None

    def validate_image_request(self, request_body: dict[str, Any]) -> None:
        """校验图片请求包含字符串模型名和非空提示词。"""

        _require_str_field(request_body, "model")
        prompt = request_body.get("prompt")
        if not isinstance(prompt, str) or not prompt:
            raise ValueError("图片请求必须提供非空 prompt")

    def validate_chat_request(self, request_body: dict[str, Any]) -> None:
        """校验文本请求包含字符串模型名和非空消息列表。"""

        _require_str_field(request_body, "model")
        messages = request_body.get("messages")
        if not isinstance(messages, list) or not messages:
            raise ValueError("文本请求必须提供非空 messages 列表")

    def validate_response_request(self, request_body: dict[str, Any]) -> None:
        """校验 Responses API 请求包含字符串模型名和非空输入。"""

        _require_str_field(request_body, "model")
        if request_body.get("input") in (None, ""):
            raise ValueError("Responses API 请求必须提供非空 input")

    def validate_request(self, request_body: dict[str, Any]) -> None:
        _require_str_field(request_body, "model")
        _require_str_field(request_body, "prompt")
        seconds = request_body.get("seconds")
        if not isinstance(seconds, int) or isinstance(seconds, bool) or seconds <= 0:
            raise ProviderError("视频请求 seconds 不合法", code="invalid_provider_request")
        _require_str_field(request_body, "size")

    def capabilities(self) -> set[str]:
        """返回当前适配器支持的平台能力集合。"""

        return {
            "image_generation",
            "image_editing",
            "chat_completion",
            "chat_stream",
            "response_creation",
            "response_stream",
            "text_to_video",
            "reference_media",
        }

    def protocol_operations(self) -> set[ProviderProtocolOperation]:
        return {
            ProviderProtocolOperation("openai_image", "create"),
            ProviderProtocolOperation("openai_image", "edit"),
            ProviderProtocolOperation("openai_text", "create"),
            ProviderProtocolOperation("openai_response", "create"),
            ProviderProtocolOperation("openai_video", "create"),
            ProviderProtocolOperation("openai_video", "retrieve"),
            ProviderProtocolOperation("openai_video", "content"),
        }

    async def generate_image(self, request_body: dict[str, Any], *, timeout: float | None = None) -> dict[str, Any]:
        """调用上游图片生成接口并返回响应体；``timeout`` 覆盖读取阶段超时秒数。"""

        self.validate_image_request(request_body)
        try:
            return await self._request_json("POST", _IMAGE_GENERATIONS_PATH, json=request_body, timeout=timeout)
        finally:
            await self._close_if_owned()

    async def edit_image(
        self, request_body: dict[str, Any], uploads: list[ProviderUpload], *, timeout: float | None = None
    ) -> dict[str, Any]:
        """以 multipart 转发输入图片并返回上游图片编辑响应体。"""

        self.validate_image_request(request_body)
        files = [
            (
                "image[]" if upload.field_name == "image" else upload.field_name,
                (upload.filename, upload.content, upload.content_type),
            )
            for upload in uploads
        ]
        data = {key: _form_value(value) for key, value in request_body.items() if value is not None}
        try:
            return await self._request_json("POST", _IMAGE_EDITS_PATH, data=data, files=files, timeout=timeout)
        finally:
            await self._close_if_owned()

    async def chat(self, request_body: dict[str, Any], *, timeout: float | None = None) -> dict[str, Any]:
        """调用上游文本补全接口并返回响应体；``timeout`` 覆盖读取阶段超时秒数。"""

        self.validate_chat_request(request_body)
        try:
            return await self._request_json("POST", _CHAT_COMPLETIONS_PATH, json=request_body, timeout=timeout)
        finally:
            await self._close_if_owned()

    async def create_response(self, request_body: dict[str, Any], *, timeout: float | None = None) -> dict[str, Any]:
        """调用上游 Responses API 并返回响应体。"""

        self.validate_response_request(request_body)
        try:
            return await self._request_json("POST", _RESPONSES_PATH, json=request_body, timeout=timeout)
        finally:
            await self._close_if_owned()

    async def submit(self, command: CreateVideoCommand) -> ProviderSubmission:
        self.validate_request(command.request_body)
        try:
            data = (await self._request_json("POST", _VIDEOS_PATH, json=command.request_body)).copy()
            task_id = data.get("id") or data.get("task_id")
            if not task_id:
                raise ProviderError("上游未返回任务标识", code="invalid_response", retryable=True)
            return ProviderSubmission(str(task_id), self._status(data.get("status", "queued")), data)
        finally:
            await self._close_if_owned()

    async def query(self, upstream_task_id: str) -> ProviderTaskSnapshot:
        try:
            data = await self._request_json("GET", f"{_VIDEOS_PATH}/{upstream_task_id}")
            return ProviderTaskSnapshot(
                self._status(data.get("status", "in_progress")),
                self._progress(data),
                data.get("url") or data.get("video_url"),
                data,
            )
        finally:
            await self._close_if_owned()

    async def cancel(self, upstream_task_id: str) -> ProviderTaskSnapshot:
        try:
            data = await self._request_json("DELETE", f"{_VIDEOS_PATH}/{upstream_task_id}")
            return ProviderTaskSnapshot(self._status(data.get("status", "cancelled")), self._progress(data), raw=data)
        finally:
            await self._close_if_owned()

    async def fetch_result(self, upstream_task_id: str) -> tuple[AsyncIterator[bytes], str]:
        try:
            url = self._url(f"{_VIDEOS_PATH}/{upstream_task_id}/content")
            response = await send_provider_request(
                self._client, "GET", url, provider_type=self.name, headers=self._auth_headers(), stream=True
            )
            await response.aread()
            log_provider_response(response, provider_type=self.name, method="GET", url=url)
            status_error = provider_error_from_status(response)
            if status_error is not None:
                raise status_error
        except httpx.HTTPError as exc:
            await self._close_if_owned()
            raise ProviderError("上游服务不可用", code="network", retryable=True) from exc
        except Exception:
            if "response" in locals():
                await response.aclose()
            await self._close_if_owned()
            raise

        async def chunks() -> AsyncIterator[bytes]:
            try:
                async for chunk in response.aiter_bytes(chunk_size=1024 * 1024):
                    yield chunk
            finally:
                await response.aclose()
                await self._close_if_owned()

        return chunks(), response.headers.get("content-type", "video/mp4")

    @staticmethod
    def _progress(data: dict[str, Any]) -> int:
        value = data.get("progress", 0)
        return max(0, min(100, int(value))) if isinstance(value, int | float) else 0

    @staticmethod
    def _status(value: str) -> ProviderTaskStatus:
        mapping = {
            "queued": ProviderTaskStatus.queued,
            "pending": ProviderTaskStatus.queued,
            "in_progress": ProviderTaskStatus.processing,
            "processing": ProviderTaskStatus.processing,
            "completed": ProviderTaskStatus.succeeded,
            "succeeded": ProviderTaskStatus.succeeded,
            "failed": ProviderTaskStatus.failed,
            "cancelled": ProviderTaskStatus.cancelled,
            "canceled": ProviderTaskStatus.cancelled,
        }
        try:
            return mapping[value]
        except KeyError as exc:
            raise ProviderError("上游返回未知任务状态", code="invalid_status") from exc

    async def open_chat_stream(self, request_body: dict[str, Any]) -> tuple[AsyncIterator[bytes], str]:
        """打开上游流式补全并返回字节迭代器和内容类型。"""

        self.validate_chat_request(request_body)
        response = await self._send_stream(_CHAT_COMPLETIONS_PATH, request_body)
        content_type = response.headers.get("content-type", "text/event-stream")

        async def chunks() -> AsyncIterator[bytes]:
            """在消费者结束、异常或完整读取后关闭 HTTP 响应和连接。"""

            try:
                async for chunk in response.aiter_bytes():
                    yield chunk
            finally:
                await response.aclose()
                await self._close_if_owned()

        return chunks(), content_type

    async def open_response_stream(self, request_body: dict[str, Any]) -> tuple[AsyncIterator[bytes], str]:
        """打开上游 Responses API 流并返回字节迭代器和内容类型。"""

        self.validate_response_request(request_body)
        response = await self._send_stream(_RESPONSES_PATH, request_body)
        content_type = response.headers.get("content-type", "text/event-stream")

        async def chunks() -> AsyncIterator[bytes]:
            try:
                async for chunk in response.aiter_bytes():
                    yield chunk
            finally:
                await response.aclose()
                await self._close_if_owned()

        return chunks(), content_type

    async def _request_json(
        self, method: str, path: str, *, timeout: float | None = None, **kwargs: Any
    ) -> dict[str, Any]:
        """发送请求并解析 JSON 对象响应，统一映射超时、网络与 HTTP 失败。"""

        if timeout is not None:
            kwargs["timeout"] = httpx.Timeout(
                connect=CONNECT_TIMEOUT_SECONDS,
                read=timeout,
                write=WRITE_TIMEOUT_SECONDS,
                pool=POOL_TIMEOUT_SECONDS,
            )
        try:
            headers = self._auth_headers()
            headers.update(kwargs.pop("headers", {}))
            response = await send_provider_request(
                self._client, method, self._url(path), provider_type=self.name, headers=headers, **kwargs
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

    async def _send_stream(self, path: str, request_body: dict[str, Any]) -> httpx.Response:
        """发送流式请求并在返回前完成状态判定，使错误可在开始响应前映射。"""

        try:
            response = await send_provider_request(
                self._client,
                "POST",
                self._url(path),
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
        base_url = self._base_url
        api_key = self._api_key
        if not isinstance(base_url, str) or not base_url or not isinstance(api_key, str) or not api_key:
            raise ProviderError("渠道 Provider 未配置凭据", code="unknown_provider", retryable=False)
        return f"{base_url}{path}"

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
