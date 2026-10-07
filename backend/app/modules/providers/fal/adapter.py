"""fal 视频 Provider 适配器。

fal 的 MiniMax H3 Max 各端点均为同步推理：POST 返回时视频已生成，响应体直接携带成品地址。
平台任务管道仍按“提交—查询—下载”编排，因此适配器把成品地址作为上游任务标识返回，查询时即视为成功，
下载时直接流式拉取该地址；渠道 URL 指向 fal 同步接口（``https://fal.run``）。
"""

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

_DEFAULT_BASE_URL = "https://fal.run"
_ENDPOINTS = {
    "minimax/h3-max/text-to-video",
    "minimax/h3-max/reference-to-video",
    "minimax/h3-max/image-to-video",
}
_RESOLUTIONS = {"480P", "768P", "1080P"}
_ASPECT_RATIOS = {"21:9", "16:9", "4:3", "1:1", "3:4", "9:16", "adaptive"}


class FalVideoProvider:
    name = "fal"
    delivers_external_result = True

    def __init__(
        self,
        base_url: str | None,
        api_key: str | None,
        provider_config: dict[str, Any] | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if base_url is not None and not base_url.startswith(("http://", "https://")):
            raise ValueError("fal 渠道 URL 必须使用 HTTP 或 HTTPS 协议")
        if not isinstance(api_key, str) or not api_key:
            raise ValueError("fal 渠道 API Key 不合法")
        self._base_url = (base_url or _DEFAULT_BASE_URL).rstrip("/")
        self._api_key = api_key
        self._endpoint, self._allowed_fields, self._field_mapping = self._parse_provider_config(provider_config)
        self._client = get_async_http_client(transport=transport)
        self._owns_client = transport is not None

    def validate_request(self, request_body: dict[str, Any]) -> None:
        endpoint = self._endpoint_from_task()
        prompt = request_body.get("prompt")
        if not isinstance(prompt, str) or not prompt:
            raise ProviderError("fal 请求必须提供非空 prompt", code="invalid_provider_request")
        mode = request_body.get("prompt_expansion_mode")
        if mode not in {"balanced", "quality"}:
            raise ProviderError("fal 请求 prompt_expansion_mode 不合法", code="invalid_provider_request")
        seconds = request_body.get("seconds")
        if seconds is not None and (
            not isinstance(seconds, int) or isinstance(seconds, bool) or not 5 <= seconds <= 15
        ):
            raise ProviderError("fal 请求 seconds 不合法", code="invalid_provider_request")
        if request_body.get("resolution") not in {None} | _RESOLUTIONS:
            raise ProviderError("fal 请求 resolution 不合法", code="invalid_provider_request")
        if request_body.get("aspect_ratio") not in {None} | _ASPECT_RATIOS:
            raise ProviderError("fal 请求 aspect_ratio 不合法", code="invalid_provider_request")
        seed = request_body.get("seed")
        if seed is not None and (not isinstance(seed, int) or isinstance(seed, bool)):
            raise ProviderError("fal 请求 seed 不合法", code="invalid_provider_request")
        self._validate_endpoint_fields(request_body, endpoint)

    def capabilities(self) -> set[str]:
        return {"text_to_video", "reference_to_video", "image_to_video"}

    def protocol_operations(self) -> set[ProviderProtocolOperation]:
        return {
            ProviderProtocolOperation("openai_video", "create"),
            ProviderProtocolOperation("openai_video", "retrieve"),
            ProviderProtocolOperation("openai_video", "content"),
        }

    async def submit(self, command: CreateVideoCommand) -> ProviderSubmission:
        """调用 fal 同步推理接口，把响应中的成品地址作为上游任务标识。"""

        try:
            self.validate_request(command.request_body)
            path = f"/{self._endpoint_from_task()}"
            data = await self._request_json("POST", path, json=self._payload(command.request_body))
            result_url = self._result_url(data)
            return ProviderSubmission(result_url, ProviderTaskStatus.succeeded, data, result_url=result_url)
        finally:
            await self._close_if_owned()

    async def query(self, upstream_task_id: str) -> ProviderTaskSnapshot:
        """同步推理在提交响应中已给出成品，查询即按已完成对待。"""

        return self._completed(upstream_task_id)

    async def cancel(self, upstream_task_id: str) -> ProviderTaskSnapshot:
        """fal 同步推理没有取消接口，任务在提交返回时已完成，按实际状态返回成功快照。"""

        return self._completed(upstream_task_id)

    async def fetch_result(self, upstream_task_id: str) -> tuple[AsyncIterator[bytes], str]:
        """按成品地址流式拉取视频，避免结果整体驻留 Worker 内存。"""

        try:
            response = await send_provider_request(
                self._client, "GET", upstream_task_id, provider_type=self.name, stream=True
            )
            status_error = provider_error_from_status(response)
            if status_error is not None:
                raise status_error
        except httpx.TimeoutException as exc:
            await self._close_if_owned()
            raise ProviderError("请求超时", code="timeout", retryable=True) from exc
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
                headers={"Authorization": f"Key {self._api_key}", "Content-Type": "application/json"},
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

    def _endpoint_from_task(self) -> str:
        if self._endpoint not in _ENDPOINTS:
            raise ProviderError("fal 任务 endpoint 未初始化", code="invalid_provider_request")
        return self._endpoint

    def _payload(self, request_body: dict[str, Any]) -> dict[str, Any]:
        """按模板白名单投影上游字段，并统一固定平台约定的可选开关。

        ``sync_mode`` 必须为 False，否则 fal 会内联返回文件内容而不是可下载直链；
        ``enable_safety_checker`` 固定关闭，内容审核由平台侧统一负责。
        """

        payload = {
            self._field_mapping.get(key, key): value
            for key, value in request_body.items()
            if key in self._allowed_fields and key != "model"
        }
        payload.update({"sync_mode": False, "enable_safety_checker": False})
        return payload

    @staticmethod
    def _completed(upstream_task_id: str) -> ProviderTaskSnapshot:
        """同步推理的成品地址即已经完成的产物，快照按成功返回。"""

        return ProviderTaskSnapshot(
            ProviderTaskStatus.succeeded,
            100,
            result_url=upstream_task_id,
            raw={"video": {"url": upstream_task_id}},
        )

    @staticmethod
    def _result_url(data: dict[str, Any]) -> str:
        """取出同步响应中的成品地址；缺失或非直链地址都视为不可重试的上游契约错误。"""

        video = data.get("video")
        result_url = video.get("url") if isinstance(video, dict) else None
        if not isinstance(result_url, str) or not result_url.startswith(("http://", "https://")):
            raise ProviderError("上游未返回视频结果地址", code="invalid_response", retryable=False)
        return result_url

    @staticmethod
    def _parse_provider_config(provider_config: dict[str, Any] | None) -> tuple[str, set[str], dict[str, str]]:
        if not isinstance(provider_config, dict):
            raise ValueError("fal 冻结模板配置不合法")
        endpoint = provider_config.get("endpoint")
        allowed_fields = provider_config.get("allowed_fields")
        field_mapping = provider_config.get("field_mapping")
        if (
            endpoint not in _ENDPOINTS
            or not isinstance(allowed_fields, list)
            or not all(isinstance(field, str) for field in allowed_fields)
            or not isinstance(field_mapping, dict)
            or not all(isinstance(source, str) and isinstance(target, str) for source, target in field_mapping.items())
        ):
            raise ValueError("fal 冻结模板配置不合法")
        return endpoint, set(allowed_fields), field_mapping

    @staticmethod
    def _validate_endpoint_fields(request_body: dict[str, Any], endpoint: str) -> None:
        if endpoint == "minimax/h3-max/reference-to-video":
            limits = {"reference_image_urls": 9, "reference_video_urls": 3, "reference_audio_urls": 3}
            total = 0
            for field, limit in limits.items():
                value = request_body.get(field)
                if value is not None and (
                    not isinstance(value, list) or not all(isinstance(item, str) and item for item in value)
                ):
                    raise ProviderError(f"fal 请求 {field} 不合法", code="invalid_provider_request")
                if value is not None and len(value) > limit:
                    raise ProviderError(f"fal 请求 {field} 数量不合法", code="invalid_provider_request")
                total += len(value or [])
            if total > 12 or (
                request_body.get("reference_audio_urls")
                and not request_body.get("reference_image_urls")
                and not request_body.get("reference_video_urls")
            ):
                raise ProviderError("fal 请求参考素材组合不合法", code="invalid_provider_request")
        if endpoint == "minimax/h3-max/image-to-video":
            image_url = request_body.get("image_url")
            if image_url is not None and (not isinstance(image_url, str) or not image_url):
                raise ProviderError("fal 请求 image_url 不合法", code="invalid_provider_request")
            end_image_url = request_body.get("end_image_url")
            if end_image_url is not None and (not isinstance(end_image_url, str) or not end_image_url):
                raise ProviderError("fal 请求 end_image_url 不合法", code="invalid_provider_request")

    async def _close_if_owned(self) -> None:
        if self._owns_client:
            await self._client.aclose()
