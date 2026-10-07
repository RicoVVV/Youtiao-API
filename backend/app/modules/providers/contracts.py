"""Provider 无关的视频生成端口及值对象。

本模块只定义应用层与上游视频服务之间的稳定协议，不包含 HTTP、鉴权或具体厂商字段映射；各 Provider 适配器负责完成这些实现细节。
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol

__all__ = [
    "CreateVideoCommand",
    "GenerationProvider",
    "ProviderError",
    "ProviderInstanceConfig",
    "ProviderSubmission",
    "ProviderTaskSnapshot",
    "ProviderTaskStatus",
    "ProviderProtocolOperation",
    "ProviderUpload",
    "VideoProvider",
]


class ProviderError(Exception):
    def __init__(
        self,
        message: str,
        *,
        code: str,
        retryable: bool = False,
        response_body: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.response_body = response_body


class ProviderTaskStatus(str, Enum):
    """跨 Provider 使用的归一化任务状态。

    适配器必须将任意厂商状态映射为本枚举，避免应用层依赖不稳定的上游状态字符串。
    """

    queued = "queued"
    processing = "processing"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


@dataclass(frozen=True)
class ProviderProtocolOperation:
    protocol_id: str
    operation_id: str


@dataclass(frozen=True)
class ProviderInstanceConfig:
    """保存创建 Provider 实例所需的冻结渠道运行参数。

    ``base_url`` 来自渠道冻结快照，``api_key`` 由 Worker 按任务冻结的渠道读取后短暂使用，``config``
    不能保存上游地址或认证数据。
    """

    provider_type: str
    config: dict[str, Any]
    base_url: str | None = None
    api_key: str | None = None


@dataclass(frozen=True)
class CreateVideoCommand:
    """提交给 Provider 的冻结创建命令。

    ``request_body`` 保持模板定义的上游字段快照，以防模板变更导致任务语义漂移。
    """

    platform_task_id: str
    request_body: dict[str, Any]


@dataclass(frozen=True)
class ProviderSubmission:
    """Provider 成功接收创建命令后返回的关联信息。

    ``upstream_task_id`` 是后续查询、取消和下载结果时唯一使用的厂商任务标识；``raw`` 仅保存必要的原始响应以支持排障。
    同步 Provider 在提交响应中直接给出成品时，额外通过 ``result_url`` 返回可下载地址，使调用方无需等待轮询即可结算。
    """

    upstream_task_id: str
    status: ProviderTaskStatus
    raw: dict[str, Any] = field(default_factory=dict)
    result_url: str | None = None


@dataclass(frozen=True)
class ProviderTaskSnapshot:
    """Provider 查询或取消结果的标准化快照。

    ``progress`` 采用 0 至 100 的统一进度尺度；``result_url`` 仅在上游已产生可下载结果时提供。
    """

    status: ProviderTaskStatus
    progress: int
    result_url: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class VideoProvider(Protocol):
    """视频 Provider 端口，定义适配器必须实现的异步调用边界。

    所有实现均以 ``name`` 作为注册表键；方法返回值必须使用本模块的归一化值对象，不能把厂商 SDK 对象泄漏到应用层。
    """

    name: str
    delivers_external_result: bool
    """为真表示上游在提交响应中直接给出可交付客户端的成品地址，平台不再下载并本地化成品。

    此时公开成品地址即上游地址，下载接口按重定向处理；为假时平台负责把成品下载到本地存储后再对外提供。
    """

    def protocol_operations(self) -> set[ProviderProtocolOperation]: ...

    def validate_request(self, request_body: dict[str, Any]) -> None:
        """校验冻结上游请求符合 Provider 执行契约。

        任务创建与 Worker 执行前均可调用；失败时抛出 ``ProviderError`` 或 ``ValueError``，不得修正请求。
        """

        ...

    def capabilities(self) -> set[str]:
        """返回适配器支持的稳定能力标识集合，供平台在提交前校验请求。"""

        ...

    async def submit(self, command: CreateVideoCommand) -> ProviderSubmission:
        """提交创建命令并返回上游任务关联信息。

        实现必须透传命令的幂等键；调用失败时抛出包含重试决策的 ``ProviderError``。
        """

        ...

    async def query(self, upstream_task_id: str) -> ProviderTaskSnapshot:
        """查询上游任务并映射为标准化快照。

        ``upstream_task_id`` 必须来自此前的提交结果；厂商状态和进度由适配器完成归一化。
        """

        ...

    async def cancel(self, upstream_task_id: str) -> ProviderTaskSnapshot:
        """请求取消上游任务并返回取消后的标准化快照。

        对已经终态的任务，适配器应按厂商语义返回其实际状态，而非伪造已取消状态。
        """

        ...

    async def fetch_result(self, upstream_task_id: str) -> tuple[AsyncIterator[bytes], str]:
        """获取已完成任务的二进制结果流和内容类型。

        返回迭代器以支持流式转发，调用方负责消费流；结果不可用或获取失败时抛出 ``ProviderError``。
        """

        ...


@dataclass(frozen=True)
class ProviderUpload:
    """同步生成请求内需要转发给上游的二进制文件。

    ``field_name`` 为上游 multipart 字段名（如 ``image``、``mask``）；``content`` 已在内存中，
    不落地磁盘，仅供单次同步请求转发使用。
    """

    field_name: str
    filename: str
    content: bytes
    content_type: str


class GenerationProvider(Protocol):
    """同步生成 Provider 端口，定义图片与文本能力的异步调用边界。

    所有实现以 ``name`` 作为注册表键；方法返回上游 OpenAI 兼容响应体或字节流，不把厂商 SDK 对象
    泄漏到应用层。适配器仅在渠道实例内短暂持有凭据。
    """

    name: str

    def protocol_operations(self) -> set[ProviderProtocolOperation]: ...

    def validate_image_request(self, request_body: dict[str, Any]) -> None:
        """校验图片请求包含 Provider 必需字段；失败时抛出 ``ValueError``，不得修正请求。"""

        ...

    def validate_chat_request(self, request_body: dict[str, Any]) -> None:
        """校验文本请求包含 Provider 必需字段；失败时抛出 ``ValueError``，不得修正请求。"""

        ...

    def validate_response_request(self, request_body: dict[str, Any]) -> None:
        """校验 Responses API 请求包含 Provider 必需字段；失败时抛出 ``ValueError``，不得修正请求。"""

        ...

    async def generate_image(self, request_body: dict[str, Any], *, timeout: float | None = None) -> dict[str, Any]:
        """同步生成图片并返回上游响应体；``timeout`` 为可选的读取阶段超时秒数覆盖，调用失败时抛出 ``ProviderError``。"""

        ...

    async def edit_image(
        self, request_body: dict[str, Any], uploads: list[ProviderUpload], *, timeout: float | None = None
    ) -> dict[str, Any]:
        """同步编辑图片并返回上游响应体；``timeout`` 为可选的读取阶段超时秒数覆盖。"""

        ...

    async def chat(self, request_body: dict[str, Any], *, timeout: float | None = None) -> dict[str, Any]:
        """同步文本补全并返回上游响应体；``timeout`` 为可选的读取阶段超时秒数覆盖，调用失败时抛出 ``ProviderError``。"""

        ...

    async def create_response(self, request_body: dict[str, Any], *, timeout: float | None = None) -> dict[str, Any]:
        """同步创建 Responses API 响应并返回上游响应体。"""

        ...

    async def open_chat_stream(self, request_body: dict[str, Any]) -> tuple[AsyncIterator[bytes], str]:
        """打开文本流式补全，返回字节迭代器和内容类型。

        实现必须在返回迭代器前完成请求发送和状态判定，使调用方能在开始流式响应前映射错误。
        """

        ...

    async def open_response_stream(self, request_body: dict[str, Any]) -> tuple[AsyncIterator[bytes], str]:
        """打开 Responses API 流式响应，返回字节迭代器和内容类型。"""

        ...
