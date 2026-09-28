"""视频领域 HTTP DTO。

本模块定义视频创建和任务查询的已发布请求响应契约及基础字段校验，不负责按数据库模型配置校验
工作流能力、持久化任务或执行上游调用。
"""

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

from app.modules.video.application.contracts import OpenAIVideoData, VideoTaskData


def _parse_openai_video_id(value: object) -> UUID:
    if not isinstance(value, str):
        raise ValueError("视频任务 ID 格式无效")
    return UUID(value.removeprefix("task_"))


OpenAIVideoId = Annotated[UUID, BeforeValidator(_parse_openai_video_id)]


class CreateVideoRequest(BaseModel):
    """接收公开模型视频创建请求并提供 HTTP 层基础校验。

    顶层仅固定 ``model``，其余动态字段原样交给应用层按当前模型版本校验；本模型不维护模型参数白名单，
    不保存数据也不调用上游服务。
    """

    model_config = ConfigDict(extra="allow")

    model: str = Field(min_length=1, max_length=64)

    def to_model_payload(self) -> dict[str, Any]:
        """返回含模型标识和全部动态顶层字段的独立解析载荷。

        返回值保留调用方提交的动态字段，字段合法性由版本化模型契约判定；调用过程不修改 DTO 本身。
        """

        return self.model_dump()


class OpenAIVideoCreateRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str = Field(min_length=1, max_length=64)


class VideoTaskDetailQuery(BaseModel):
    task_id: UUID


class VideoTaskResponse(BaseModel):
    """平台视频任务的安全只读投影，供创建和查询接口复用。

    仅暴露调用方需要的生命周期、进度、时间、媒体地址和脱敏错误信息；不包含上游请求、配置版本或认证数据。
    """

    id: str
    model: str
    status: str
    progress: float = Field(ge=0, le=100)
    created_at: datetime
    completed_at: datetime | None = None
    result_url: str | None = None
    error: dict[str, Any] | None = None

    @classmethod
    def from_task_data(cls, data: VideoTaskData) -> "VideoTaskResponse":
        """将视频应用层安全投影转换为已发布的 HTTP 响应 DTO。

        参数 ``data`` 为不含 HTTP 框架依赖的内部任务投影；返回值保持公开接口字段与序列化行为。
        本方法不访问数据库且不会修改任务或投影。
        """

        return cls(
            id=data.id,
            model=data.model,
            status=data.status,
            progress=data.progress,
            created_at=data.created_at,
            completed_at=data.completed_at,
            result_url=data.result_url,
            error=data.error,
        )


class OpenAIVideoError(BaseModel):
    code: str
    message: str


class OpenAIVideoResponse(BaseModel):
    id: str
    object: Literal["video"] = "video"
    model: str
    status: Literal["queued", "in_progress", "completed", "failed"]
    progress: int = Field(ge=0, le=100)
    created_at: int
    result_url: str | None = None
    error: OpenAIVideoError | None = None
    cost: str | None = None
    balance: str | None = None
    reference_tokens: str | None = None

    @classmethod
    def from_openai_data(cls, data: OpenAIVideoData) -> "OpenAIVideoResponse":
        return cls(
            id=data.id,
            model=data.model,
            status=data.status,
            progress=data.progress,
            created_at=int(data.created_at.timestamp()),
            result_url=data.result_url,
            error=OpenAIVideoError(**data.error) if data.error is not None else None,
            cost=data.cost,
            balance=data.balance,
            reference_tokens=data.reference_tokens,
        )
