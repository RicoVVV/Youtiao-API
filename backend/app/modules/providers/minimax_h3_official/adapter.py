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
from app.modules.providers.http_support import provider_error_from_status, send_provider_request

_RESOLUTIONS = {"768P", "2K"}
_RATIOS = {"1:1", "2:3", "3:2", "3:4", "4:3", "9:16", "16:9", "21:9", "adaptive"}
_MEDIA_FIELDS = {
    "images": ("image_url", "reference_image"),
    "input_reference": ("image_url", "first_frame"),
    "reference_video": ("video_url", "reference_video"),
    "reference_videos": ("video_url", "reference_video"),
    "reference_audio": ("audio_url", "reference_audio"),
    "reference_audios": ("audio_url", "reference_audio"),
}


class MiniMaxH3OfficialProvider:
    name = "minimax_h3_official"
    delivers_external_result = False

    def __init__(
        self,
        base_url: str | None,
        api_key: str | None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not isinstance(base_url, str) or not base_url.startswith(("http://", "https://")):
            raise ValueError("MiniMax 官方渠道 URL 必须使用 HTTP 或 HTTPS 协议")
        if not isinstance(api_key, str) or not api_key:
            raise ValueError("MiniMax 官方渠道 API Key 不合法")
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._client = get_async_http_client(transport=transport)
        self._owns_client = transport is not None

    def validate_request(self, request_body: dict[str, Any]) -> None:
        model = request_body.get("model", "MiniMax-H3")
        prompt = request_body.get("prompt")
        duration = request_body.get("seconds", request_body.get("duration"))
        resolution = request_body.get("resolution") or self._resolution(request_body.get("size"))
        ratio = request_body.get("aspect_ratio", request_body.get("ratio"))
        if model not in {"MiniMax-H3", "MiniMax-H3-Max"}:
            raise ProviderError("MiniMax 官方 model 不合法", code="invalid_provider_request")
        if not isinstance(prompt, str) or not prompt:
            raise ProviderError("MiniMax 官方请求必须提供非空 prompt", code="invalid_provider_request")
        if not isinstance(duration, int) or isinstance(duration, bool) or not 4 <= duration <= 15:
            raise ProviderError("MiniMax 官方请求 seconds 不合法", code="invalid_provider_request")
        if resolution not in _RESOLUTIONS:
            raise ProviderError("MiniMax 官方请求 resolution 不合法", code="invalid_provider_request")
        if ratio is not None and ratio not in _RATIOS:
            raise ProviderError("MiniMax 官方请求 aspect_ratio 不合法", code="invalid_provider_request")
        self._validate_media(request_body)
        has_reference = any(
            request_body.get(field)
            for field in ("images", "reference_video", "reference_videos", "reference_audio", "reference_audios")
        )
        if has_reference and request_body.get("input_reference"):
            raise ProviderError("MiniMax 官方请求参考素材组合不合法", code="invalid_provider_request")
        if has_reference and request_body.get("aspect_ratio") not in (None, "adaptive"):
            raise ProviderError("MiniMax 官方参考素材请求 ratio 必须为 adaptive", code="invalid_provider_request")

    def capabilities(self) -> set[str]:
        return {"text_to_video", "reference_to_video", "image_to_video"}

    def protocol_operations(self) -> set[ProviderProtocolOperation]:
        return {
            ProviderProtocolOperation("openai_video", "create"),
            ProviderProtocolOperation("openai_video", "retrieve"),
            ProviderProtocolOperation("openai_video", "content"),
        }

    async def submit(self, command: CreateVideoCommand) -> ProviderSubmission:
        try:
            self.validate_request(command.request_body)
            data = await self._request_json("POST", "/v2/video_generation", json=self._payload(command.request_body))
            task_id = data.get("task_id")
            if not isinstance(task_id, str) or not task_id:
                raise ProviderError("上游未返回任务标识", code="invalid_response", retryable=True)
            return ProviderSubmission(task_id, ProviderTaskStatus.queued, data)
        finally:
            await self._close_if_owned()

    async def query(self, upstream_task_id: str) -> ProviderTaskSnapshot:
        try:
            data = await self._request_json("GET", f"/v2/query/video_generation/{upstream_task_id}")
            task = data.get("task", data)
            if not isinstance(task, dict) or not isinstance(task.get("status"), str):
                raise ProviderError("上游返回未知任务结构", code="invalid_response", retryable=True)
            status = self._status(task["status"])
            content = task.get("content")
            result_url = content.get("url") if isinstance(content, dict) else None
            return ProviderTaskSnapshot(status, 100 if status is ProviderTaskStatus.succeeded else 0, result_url, data)
        finally:
            await self._close_if_owned()

    async def cancel(self, upstream_task_id: str) -> ProviderTaskSnapshot:
        raise ProviderError("MiniMax 官方 V2 不支持取消任务", code="unsupported_operation", retryable=False)

    async def fetch_result(self, upstream_task_id: str) -> tuple[AsyncIterator[bytes], str]:
        try:
            data = await self._request_json("GET", f"/v2/query/video_generation/{upstream_task_id}")
            task = data.get("task", data)
            content = task.get("content") if isinstance(task, dict) else None
            result_url = content.get("url") if isinstance(content, dict) else None
            if (
                not isinstance(task, dict)
                or self._status(task.get("status", "")).value != "succeeded"
                or not result_url
            ):
                raise ProviderError("上游未返回视频结果地址", code="invalid_response", retryable=True)
            response = await send_provider_request(
                self._client, "GET", result_url, provider_type=self.name, stream=True
            )
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

    async def _request_json(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = await send_provider_request(
                self._client,
                method,
                f"{self._base_url}{path}",
                provider_type=self.name,
                headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                **kwargs,
            )
        except httpx.HTTPError as exc:
            raise ProviderError("上游服务不可用", code="network", retryable=True) from exc
        status_error = provider_error_from_status(response)
        if status_error is not None:
            raise status_error
        payload = response.json()
        if not isinstance(payload, dict):
            raise ProviderError("上游返回未知响应结构", code="invalid_response", retryable=True)
        return payload

    def _payload(self, request_body: dict[str, Any]) -> dict[str, Any]:
        content = [{"type": "text", "text": request_body["prompt"]}]
        for field, (content_type, role) in _MEDIA_FIELDS.items():
            values = request_body.get(field)
            if values is None:
                continue
            if not isinstance(values, list):
                values = [values]
            for index, value in enumerate(values):
                item: dict[str, Any] = {"type": content_type, "role": role}
                item[content_type] = {"url": value}
                if field == "images" and len(values) == 2:
                    item["role"] = "first_frame" if index == 0 else "last_frame"
                content.append(item)
        payload = {
            "model": request_body.get("model", "MiniMax-H3"),
            "content": content,
            "resolution": self._resolution(request_body.get("size") or request_body.get("resolution")),
            "duration": request_body.get("seconds", request_body.get("duration")),
        }
        ratio = request_body.get("aspect_ratio", request_body.get("ratio"))
        if ratio is not None:
            payload["ratio"] = ratio
        for field in ("callback_url", "aigc_watermark"):
            if field in request_body:
                payload[field] = request_body[field]
        return payload

    @staticmethod
    def _resolution(value: Any) -> str | None:
        if value in {"2K", "4K"}:
            return "2K"
        if isinstance(value, str) and "x" in value:
            return "768P"
        return value

    @staticmethod
    def _validate_media(request_body: dict[str, Any]) -> None:
        for field, (_, _) in _MEDIA_FIELDS.items():
            value = request_body.get(field)
            if value is None:
                continue
            values = value if isinstance(value, list) else [value]
            if not values or not all(
                isinstance(item, str) and item.startswith(("http://", "https://")) for item in values
            ):
                raise ProviderError(f"MiniMax 官方请求 {field} 不合法", code="invalid_provider_request")
        if any(
            len(request_body.get(field, [])) > limit
            for field, limit in (("images", 9), ("reference_videos", 3), ("reference_audios", 3))
            if isinstance(request_body.get(field, []), list)
        ):
            raise ProviderError("MiniMax 官方请求参考素材数量不合法", code="invalid_provider_request")

    @staticmethod
    def _status(value: str) -> ProviderTaskStatus:
        try:
            return {
                "queued": ProviderTaskStatus.queued,
                "running": ProviderTaskStatus.processing,
                "succeeded": ProviderTaskStatus.succeeded,
                "failed": ProviderTaskStatus.failed,
                "cancelled": ProviderTaskStatus.cancelled,
            }[value.lower()]
        except KeyError as exc:
            raise ProviderError("上游返回未知任务状态", code="invalid_status") from exc

    async def _close_if_owned(self) -> None:
        if self._owns_client:
            await self._client.aclose()
