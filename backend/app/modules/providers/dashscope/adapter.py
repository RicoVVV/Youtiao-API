"""DashScope 原生 Generation 与视频生成 Provider 适配器。

适配器把平台文本生成端口映射到千问 DashScope 的原生 Generation 接口，按渠道冻结配置拼接地址并以
``Authorization: Bearer`` 鉴权；请求体保持 DashScope 原生 ``input``/``parameters`` 结构，响应与流式
事件原样返回。凭据仅保留在实例内存中，不写入日志或快照。

纯文本与多模态共用同一公开协议族，端点由公开路径决定：路由把平台内部字段
``ENDPOINT_FIELD`` 注入请求体，适配器据此选择端点并在转发前剥离该字段，上游不会收到
平台内部字段，客户端也无法通过请求体自行改变端点。

视频能力映射到百炼万相异步任务接口：提交时把平台素材字段投影为万相 ``input.media`` 并携带
``X-DashScope-Async: enable``，查询与下载统一读 DashScope 异步任务接口的状态与成品地址。成品地址是
有效期有限的临时地址，因此平台按本地化交付处理，由平台下载后再对外提供，不直接把上游地址交给客户端。
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
from app.modules.providers.contracts import (
    CreateVideoCommand,
    ProviderError,
    ProviderProtocolOperation,
    ProviderSubmission,
    ProviderTaskSnapshot,
    ProviderTaskStatus,
    ProviderUpload,
)
from app.modules.providers.http_support import provider_error_from_status, send_provider_request

ENDPOINT_FIELD = "_dashscope_endpoint"

TEXT_GENERATION_PATH = "/api/v1/services/aigc/text-generation/generation"
MULTIMODAL_GENERATION_PATH = "/api/v1/services/aigc/multimodal-generation/generation"
VIDEO_SYNTHESIS_PATH = "/api/v1/services/aigc/video-generation/video-synthesis"
TASK_PATH = "/api/v1/tasks"

TEXT_ENDPOINT = "text"
MULTIMODAL_ENDPOINT = "multimodal"
_ENDPOINT_PATHS = {
    TEXT_ENDPOINT: TEXT_GENERATION_PATH,
    MULTIMODAL_ENDPOINT: MULTIMODAL_GENERATION_PATH,
}

_ASYNC_HEADER = "X-DashScope-Async"
"""万相视频接口只支持异步调用，缺少该请求头会被上游直接拒绝。"""

_VIDEO_MODELS = ("wan3.0-video", "wan3.0-video-prime")
"""万相 3.0 标准版与高速版；上游模型名由渠道模型映射决定，其余模型不在本适配器能力内。"""

_VIDEO_DURATION_RANGE = (2, 30)
_VIDEO_RESOLUTIONS = ("480P", "720P", "1080P")
_VIDEO_ASPECT_RATIOS = ("adaptive", "16:9", "4:3", "1:1", "3:4", "9:16")
_VIDEO_PROMPT_MAX_LENGTH = 20000
_VIDEO_SEED_MAX = 2147483647

_MEDIA_FIELDS = {
    "first_image": ("first_frame", 1),
    "last_image": ("last_frame", 1),
    "reference_images": ("reference_image", 10),
    "reference_videos": ("reference_video", 5),
    "reference_audios": ("reference_audio", 5),
    "reference_file": ("file", 1),
    "web_link": ("link", 1),
}
"""平台素材字段到万相 ``input.media[].type`` 的映射及各自数量上限。"""

_FRAME_FIELDS = ("first_image", "last_image")
_REFERENCE_FIELDS = ("reference_images", "reference_videos", "reference_audios", "reference_file", "web_link")
"""首尾帧模式与参考素材、文档、网页链接是上游声明的互斥用法，同一次请求不得混用。"""

_DOCUMENT_FIELDS = ("reference_file", "web_link")
"""文档与网页链接二者互斥，各自最多 1 个。"""

_PARAMETER_FIELDS = {
    "seconds": "duration",
    "resolution": "resolution",
    "aspect_ratio": "ratio",
    "seed": "seed",
    "generate_audio": "audio",
    "prompt_extend": "prompt_extend",
    "watermark": "watermark",
}
_SWITCH_FIELDS = ("generate_audio", "prompt_extend", "watermark")
_VIDEO_STATUSES = {
    "pending": ProviderTaskStatus.queued,
    "running": ProviderTaskStatus.processing,
    "succeeded": ProviderTaskStatus.succeeded,
    "failed": ProviderTaskStatus.failed,
    "canceled": ProviderTaskStatus.cancelled,
    "cancelled": ProviderTaskStatus.cancelled,
    # 上游把「任务不存在或已过期」也归入该状态，任务此时已不可恢复，按失败处理避免任务挂起。
    "unknown": ProviderTaskStatus.failed,
}


class DashScopeProvider:
    """把平台文本生成端口映射到按请求路径选定的 DashScope Generation 端点，并承载万相视频异步任务。"""

    name = "dashscope"

    delivers_external_result = False
    """万相成品地址是上游有效期有限的临时地址，必须由平台下载本地化后再对外提供。"""

    def __init__(
        self,
        base_url: str | None,
        api_key: str | None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """使用冻结渠道配置构造客户端。

        参数：base_url、api_key 来自冻结渠道配置；transport 仅用于测试替换传输。
        返回值：无。
        副作用：Provider 密钥仅保留在进程内存中。
        """

        self._base_url = base_url.rstrip("/") if isinstance(base_url, str) and base_url else None
        self._api_key = api_key if isinstance(api_key, str) and api_key else None
        self._client = get_async_http_client(transport=transport)
        self._owns_client = transport is not None

    def validate_image_request(self, request_body: dict[str, Any]) -> None:
        raise ValueError("DashScope Provider 不支持 OpenAI 图片接口")

    def validate_response_request(self, request_body: dict[str, Any]) -> None:
        raise ValueError("DashScope Provider 不支持 OpenAI Responses API")

    def validate_chat_request(self, request_body: dict[str, Any]) -> None:
        """校验 DashScope 请求包含模型名与非空 ``input.messages``。"""

        _require_str_field(request_body, "model")
        input_body = request_body.get("input")
        messages = input_body.get("messages") if isinstance(input_body, dict) else None
        if not isinstance(messages, list) or not messages:
            raise ValueError("DashScope 请求必须提供非空 input.messages")

    def validate_request(self, request_body: dict[str, Any]) -> None:
        """按万相契约复核冻结请求：模型、生成参数与素材组合都必须在上游能力范围内。"""

        model = request_body.get("model")
        if not isinstance(model, str) or model not in _VIDEO_MODELS:
            raise ProviderError("DashScope 视频请求 model 不合法", code="invalid_provider_request")
        prompt = request_body.get("prompt")
        if prompt is not None and (not isinstance(prompt, str) or not prompt or len(prompt) > _VIDEO_PROMPT_MAX_LENGTH):
            raise ProviderError("DashScope 视频请求 prompt 不合法", code="invalid_provider_request")
        media = _video_media(request_body)
        if prompt is None and not media:
            raise ProviderError("DashScope 视频请求必须提供 prompt 或媒体素材", code="invalid_provider_request")
        seconds = request_body.get("seconds")
        minimum_seconds, maximum_seconds = _VIDEO_DURATION_RANGE
        if (
            not isinstance(seconds, int)
            or isinstance(seconds, bool)
            or not minimum_seconds <= seconds <= maximum_seconds
        ):
            raise ProviderError("DashScope 视频请求 seconds 不合法", code="invalid_provider_request")
        if request_body.get("resolution") not in _VIDEO_RESOLUTIONS:
            raise ProviderError("DashScope 视频请求 resolution 不合法", code="invalid_provider_request")
        ratio = request_body.get("aspect_ratio")
        if ratio is not None and ratio not in _VIDEO_ASPECT_RATIOS:
            raise ProviderError("DashScope 视频请求 aspect_ratio 不合法", code="invalid_provider_request")
        seed = request_body.get("seed")
        if seed is not None and (
            # 上游以 ``-1`` 表示由系统随机生成种子，与显式取值范围一并接受。
            not isinstance(seed, int) or isinstance(seed, bool) or not -1 <= seed <= _VIDEO_SEED_MAX
        ):
            raise ProviderError("DashScope 视频请求 seed 不合法", code="invalid_provider_request")
        for field in _SWITCH_FIELDS:
            value = request_body.get(field)
            if value is not None and not isinstance(value, bool):
                raise ProviderError("DashScope 视频请求开关字段不合法", code="invalid_provider_request")
        if any(request_body.get(field) for field in _FRAME_FIELDS) and any(
            request_body.get(field) for field in _REFERENCE_FIELDS
        ):
            raise ProviderError("DashScope 视频请求素材组合不合法", code="invalid_provider_request")
        if all(request_body.get(field) for field in _DOCUMENT_FIELDS):
            raise ProviderError("DashScope 视频请求素材组合不合法", code="invalid_provider_request")

    def protocol_operations(self) -> set[ProviderProtocolOperation]:
        return {
            ProviderProtocolOperation("dashscope_text", "create"),
            ProviderProtocolOperation("dashscope_multimodal", "create"),
            ProviderProtocolOperation("openai_video", "create"),
            ProviderProtocolOperation("openai_video", "retrieve"),
            ProviderProtocolOperation("openai_video", "content"),
        }

    def capabilities(self) -> set[str]:
        return {
            "dashscope_generation",
            "dashscope_stream",
            "text_to_video",
            "image_to_video",
            "reference_to_video",
        }

    async def generate_image(self, request_body: dict[str, Any], *, timeout: float | None = None) -> dict[str, Any]:
        raise ValueError("DashScope Provider 不支持 OpenAI 图片接口")

    async def edit_image(
        self, request_body: dict[str, Any], uploads: list[ProviderUpload], *, timeout: float | None = None
    ) -> dict[str, Any]:
        raise ValueError("DashScope Provider 不支持 OpenAI 图片接口")

    async def create_response(self, request_body: dict[str, Any], *, timeout: float | None = None) -> dict[str, Any]:
        raise ValueError("DashScope Provider 不支持 OpenAI Responses API")

    async def chat(self, request_body: dict[str, Any], *, timeout: float | None = None) -> dict[str, Any]:
        """调用 DashScope Generation 接口并返回原生响应体。"""

        self.validate_chat_request(request_body)
        url = self._url(_endpoint(request_body))
        body = _upstream_body(request_body)
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
                url,
                provider_type=self.name,
                headers=self._headers(),
                json=body,
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

    async def open_chat_stream(self, request_body: dict[str, Any]) -> tuple[AsyncIterator[bytes], str]:
        """开启 DashScope 增量输出并返回 SSE 字节流和内容类型。"""

        self.validate_chat_request(request_body)
        endpoint_url = self._url(_endpoint(request_body))
        try:
            response = await send_provider_request(
                self._client,
                "POST",
                endpoint_url,
                provider_type=self.name,
                headers=self._headers(stream=True),
                json=_upstream_body(request_body),
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

    async def open_response_stream(self, request_body: dict[str, Any]) -> tuple[AsyncIterator[bytes], str]:
        raise ValueError("DashScope Provider 不支持 OpenAI Responses API")

    async def submit(self, command: CreateVideoCommand) -> ProviderSubmission:
        """提交万相异步任务，上游只返回任务标识与初始状态。"""

        try:
            self.validate_request(command.request_body)
            data = await self._request_json(
                "POST",
                VIDEO_SYNTHESIS_PATH,
                headers=self._video_headers(),
                json=self._video_body(command.request_body),
            )
            output = _video_output(data)
            task_id = output.get("task_id")
            if not isinstance(task_id, str) or not task_id:
                raise ProviderError("上游未返回任务标识", code="invalid_response", retryable=True)
            return ProviderSubmission(task_id, self._video_status(output.get("task_status")), data)
        finally:
            await self._close_if_owned()

    async def query(self, upstream_task_id: str) -> ProviderTaskSnapshot:
        """查询万相任务并映射为平台统一状态快照。"""

        try:
            data = await self._request_json("GET", f"{TASK_PATH}/{upstream_task_id}")
            output = _video_output(data)
            status = self._video_status(output.get("task_status"))
            return ProviderTaskSnapshot(
                status,
                100 if status is ProviderTaskStatus.succeeded else 0,
                _video_result_url(output),
                data,
            )
        finally:
            await self._close_if_owned()

    async def cancel(self, upstream_task_id: str) -> ProviderTaskSnapshot:
        """DashScope 异步任务接口未提供取消能力。"""

        raise ProviderError("上游视频服务不支持取消任务", code="unsupported_operation")

    async def fetch_result(self, upstream_task_id: str) -> tuple[AsyncIterator[bytes], str]:
        """重新查询任务取有效期内的成品地址，并流式拉取视频避免整体驻留内存。"""

        try:
            data = await self._request_json("GET", f"{TASK_PATH}/{upstream_task_id}")
            output = _video_output(data)
            result_url = _video_result_url(output)
            if self._video_status(output.get("task_status")) is not ProviderTaskStatus.succeeded or not result_url:
                raise ProviderError("上游未返回视频结果地址", code="invalid_response", retryable=True)
            # 成品地址是上游临时地址，凭签名参数即可访问，不下发平台凭据以避开对象存储的鉴权冲突。
            response = await send_provider_request(
                self._client, "GET", result_url, provider_type=self.name, stream=True
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

    def _url(self, path: str) -> str:
        if not isinstance(self._base_url, str) or not self._base_url or not self._api_key:
            raise ProviderError("渠道 Provider 未配置凭据", code="unknown_provider", retryable=False)
        return f"{self._base_url}{path}"

    def _headers(self, *, stream: bool = False) -> dict[str, str]:
        if not isinstance(self._api_key, str) or not self._api_key:
            raise ProviderError("渠道 Provider 未配置凭据", code="unknown_provider", retryable=False)
        headers = {"Authorization": f"Bearer {self._api_key}"}
        if stream:
            headers["X-DashScope-SSE"] = "enable"
        return headers

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """调用 DashScope 并把网络与 HTTP 失败映射为不含敏感信息的 Provider 异常。"""

        try:
            response = await send_provider_request(
                self._client,
                method,
                self._url(path),
                provider_type=self.name,
                headers=headers or self._headers(),
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

    def _video_headers(self) -> dict[str, str]:
        """视频接口只支持异步调用，提交请求必须显式开启异步。"""

        return {**self._headers(), _ASYNC_HEADER: "enable"}

    def _video_body(self, request_body: dict[str, Any]) -> dict[str, Any]:
        """把平台视频请求投影为万相原生 ``input``/``parameters`` 结构。

        只投影模板声明的字段，平台内部字段与未声明字段都不会出现在上游请求里。
        """

        input_body: dict[str, Any] = {}
        prompt = request_body.get("prompt")
        if isinstance(prompt, str) and prompt:
            input_body["prompt"] = prompt
        media = _video_media(request_body)
        if media:
            input_body["media"] = media
        parameters = {
            upstream_field: request_body[field]
            for field, upstream_field in _PARAMETER_FIELDS.items()
            if request_body.get(field) is not None
        }
        payload: dict[str, Any] = {"model": request_body.get("model"), "input": input_body}
        if parameters:
            payload["parameters"] = parameters
        return payload

    @staticmethod
    def _video_status(value: Any) -> ProviderTaskStatus:
        """把万相任务状态映射为平台归一化状态。"""

        try:
            return _VIDEO_STATUSES[value.lower()]
        except (AttributeError, KeyError) as exc:
            raise ProviderError("上游返回未知任务状态", code="invalid_status") from exc

    async def _close_if_owned(self) -> None:
        """仅关闭测试注入传输时创建的独立客户端，不关闭进程共享客户端。"""

        if self._owns_client:
            await self._client.aclose()


def _endpoint(request_body: dict[str, Any]) -> str:
    """按路由注入的平台内部字段返回端点路径，缺失时按纯文本端点处理。"""

    value = request_body.get(ENDPOINT_FIELD)
    if value is None:
        return TEXT_GENERATION_PATH
    if not isinstance(value, str) or value not in _ENDPOINT_PATHS:
        raise ValueError("DashScope 端点类型不合法")
    return _ENDPOINT_PATHS[value]


def _upstream_body(request_body: dict[str, Any]) -> dict[str, Any]:
    """剥离平台内部字段，保证上游只收到 DashScope 原生请求体。"""

    return {key: value for key, value in request_body.items() if key != ENDPOINT_FIELD}


def _video_media(request_body: dict[str, Any]) -> list[dict[str, str]]:
    """把平台素材字段展开为万相 ``media`` 数组，数量或地址不合规时拒绝请求。

    展开顺序与字段声明一致：首帧、尾帧、参考图、参考视频、参考音频、文档、网页链接；上游按图、视频、
    音频分别在同类素材内计数，因此提示词中的「图1」「视频1」「音频1」与顺序一一对应。
    """

    media: list[dict[str, str]] = []
    for field, (media_type, limit) in _MEDIA_FIELDS.items():
        value = request_body.get(field)
        if value is None:
            continue
        values = value if isinstance(value, list) else [value]
        if not values or len(values) > limit:
            raise ProviderError("DashScope 视频请求素材数量不合法", code="invalid_provider_request")
        for url in values:
            if not _is_media_url(url):
                raise ProviderError("DashScope 视频请求素材地址不合法", code="invalid_provider_request")
            media.append({"type": media_type, "url": url})
    return media


def _video_output(payload: dict[str, Any]) -> dict[str, Any]:
    """取异步任务响应中的 ``output`` 对象，结构缺失时视为上游异常响应。"""

    output = payload.get("output")
    if not isinstance(output, dict):
        raise ProviderError("上游返回未知任务结构", code="invalid_response", retryable=True)
    return output


def _video_result_url(output: dict[str, Any]) -> str | None:
    """取任务成功后的成品地址，未出片时返回空值。"""

    result_url = output.get("video_url")
    return result_url if isinstance(result_url, str) and result_url else None


def _is_media_url(value: Any) -> bool:
    """素材地址必须是上游服务端可访问的 HTTP(S) 地址。"""

    return isinstance(value, str) and value.startswith(("http://", "https://"))


def _require_str_field(request_body: dict[str, Any], field: str) -> str:
    value = request_body.get(field)
    if not isinstance(value, str) or not value:
        raise ValidationError(
            f"请求必须提供非空 {field}", code="contract.non_empty_field_required", params={"name": field}
        )
    return value
