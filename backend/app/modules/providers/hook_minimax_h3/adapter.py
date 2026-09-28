"""MiniMax H3 HTTP 适配器，隔离 Provider 专有请求、状态和错误契约。"""

from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.infrastructure.http.client import get_async_http_client
from app.modules.providers.contracts import (
    CreateVideoCommand,
    ProviderError,
    ProviderProtocolOperation,
    ProviderSubmission,
    ProviderTaskSnapshot,
    ProviderTaskStatus,
)
from app.modules.providers.hook_minimax_h3.templates import MINIMAX_H3_DEFAULT_TEMPLATE
from app.modules.providers.http_support import (
    log_provider_response,
    provider_error_from_status,
    send_provider_request,
)


class H3VideoProvider:
    """把统一视频 Provider 端口映射为 MiniMax H3 HTTP 接口。"""

    name = "minimax_h3"
    delivers_external_result = False
    _request_fields = {"model", *MINIMAX_H3_DEFAULT_TEMPLATE.input_schema["properties"]}

    def __init__(
        self,
        base_url: str | None,
        api_key: str | None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """使用冻结渠道配置构造 H3 客户端并可选接收测试 HTTP 传输层。

        参数：base_url 与 api_key 必须来自冻结渠道配置，transport 仅用于测试替换网络传输。
        返回值：无。
        副作用：Provider 密钥仅保留在 Worker 进程内存中。
        """

        if not isinstance(base_url, str) or not base_url.startswith(("http://", "https://")):
            raise ValueError("H3 渠道 URL 必须使用 HTTP 或 HTTPS 协议")
        if not isinstance(api_key, str) or not api_key:
            raise ValueError("H3 渠道 API Key 不合法")
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._client = get_async_http_client(transport=transport)
        self._owns_client = transport is not None

    def validate_request(self, request_body: dict[str, Any]) -> None:
        """验证冻结 H3 请求的核心字段类型，防止无效快照被重复提交。"""

        expected_types = {"model": str, "prompt": str, "seconds": int, "size": str}
        for field, expected_type in expected_types.items():
            value = request_body.get(field)
            if not isinstance(value, expected_type) or isinstance(value, bool):
                raise ProviderError("冻结 H3 请求不符合契约", code="invalid_provider_request")

    def capabilities(self) -> set[str]:
        """返回当前 H3 适配器支持的平台能力集合。"""

        return {"text_to_video", "reference_media"}

    def protocol_operations(self) -> set[ProviderProtocolOperation]:
        return {
            ProviderProtocolOperation("openai_video", "create"),
            ProviderProtocolOperation("openai_video", "retrieve"),
            ProviderProtocolOperation("openai_video", "content"),
        }

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        """调用 H3 并将网络与 HTTP 失败映射为不含敏感信息的 Provider 异常。"""

        try:
            headers = {"Authorization": f"Bearer {self._api_key}"}
            headers.update(kwargs.pop("headers", {}))
            response = await send_provider_request(
                self._client,
                method,
                f"{self._base_url}{path}",
                provider_type=self.name,
                headers=headers,
                **kwargs,
            )
        except httpx.HTTPError as exc:
            raise ProviderError("上游服务不可用", code="network", retryable=True) from exc
        status_error = provider_error_from_status(response)
        if status_error is not None:
            raise status_error
        return response

    async def submit(self, command: CreateVideoCommand) -> ProviderSubmission:
        """提交冻结请求体并返回标准化上游任务关联信息。"""

        try:
            self.validate_request(command.request_body)
            request_body = {
                field: command.request_body[field] for field in self._request_fields if field in command.request_body
            }
            data = (
                await self._request(
                    "POST",
                    "/v1/videos",
                    json=request_body,
                )
            ).json()
            task_id = data.get("task_id") or data.get("id")
            if not task_id:
                raise ProviderError("上游未返回任务标识", code="invalid_response", retryable=True)
            return ProviderSubmission(str(task_id), self._status(data.get("status", "queued")), data)
        finally:
            if self._owns_client:
                await self._client.aclose()

    async def query(self, upstream_task_id: str) -> ProviderTaskSnapshot:
        """查询 H3 任务并返回平台无关状态快照。"""

        try:
            data = (await self._request("GET", f"/v1/videos/{upstream_task_id}")).json()
            return ProviderTaskSnapshot(
                self._status(data.get("status", "processing")),
                int(data.get("progress", 0)),
                data.get("url") or data.get("video_url"),
                data,
            )
        finally:
            if self._owns_client:
                await self._client.aclose()

    async def cancel(self, upstream_task_id: str) -> ProviderTaskSnapshot:
        """取消 H3 任务并返回标准化状态快照。"""

        try:
            data = (await self._request("POST", f"/v1/videos/{upstream_task_id}/cancel")).json()
            return ProviderTaskSnapshot(
                self._status(data.get("status", "cancelled")), int(data.get("progress", 0)), raw=data
            )
        finally:
            if self._owns_client:
                await self._client.aclose()

    async def fetch_result(self, upstream_task_id: str) -> tuple[AsyncIterator[bytes], str]:
        """以流式迭代器读取 H3 成品，避免视频内容整体常驻 Worker 内存。"""

        try:
            url = f"{self._base_url}/v1/videos/{upstream_task_id}/content"
            response = await send_provider_request(
                self._client,
                "GET",
                url,
                provider_type=self.name,
                headers={"Authorization": f"Bearer {self._api_key}"},
                stream=True,
            )
            await response.aread()
            log_provider_response(response, provider_type=self.name, method="GET", url=url)
            status_error = provider_error_from_status(response)
            if status_error is not None:
                raise status_error
        except httpx.HTTPError as exc:
            if self._owns_client:
                await self._client.aclose()
            raise ProviderError("上游服务不可用", code="network", retryable=True) from exc
        except Exception:
            if "response" in locals():
                await response.aclose()
            if self._owns_client:
                await self._client.aclose()
            raise

        async def chunks() -> AsyncIterator[bytes]:
            """在消费者结束、异常或完整读取后关闭 HTTP 响应和连接。"""

            try:
                async for chunk in response.aiter_bytes(chunk_size=1024 * 1024):
                    yield chunk
            finally:
                await response.aclose()
                if self._owns_client:
                    await self._client.aclose()

        return chunks(), response.headers.get("content-type", "video/mp4")

    def _status(self, value: str) -> ProviderTaskStatus:
        """将 H3 状态词汇映射为平台统一状态。"""

        mapping = {
            "pending": ProviderTaskStatus.queued,
            "queued": ProviderTaskStatus.queued,
            "in_progress": ProviderTaskStatus.processing,
            "processing": ProviderTaskStatus.processing,
            "completed": ProviderTaskStatus.succeeded,
            "succeeded": ProviderTaskStatus.succeeded,
            "failed": ProviderTaskStatus.failed,
            "cancelled": ProviderTaskStatus.cancelled,
        }
        try:
            return mapping[value]
        except KeyError as exc:
            raise ProviderError("上游返回未知任务状态", code="invalid_status") from exc
