"""管理员视频任务 API 的请求数据传输对象。"""

from uuid import UUID

from pydantic import BaseModel, Field


class AdminCancelVideoTaskRequest(BaseModel):
    """描述管理员取消视频任务时必须提供的审计原因。

    参数：task_id 为待取消任务标识，reason 为受长度限制的人工取消原因。
    返回值：本模型仅承载请求数据。
    副作用：无；原因会由应用服务写入任务审计事件。
    """

    task_id: UUID
    reason: str = Field(min_length=1, max_length=256, description="管理员取消任务的简短安全原因")
