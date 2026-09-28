"""视频任务、阶段执行及审计事件的 ORM 映射。

本模块只定义视频领域的 PostgreSQL 持久化结构及对象关联，不承载状态迁移、计费或上游调用逻辑；
任务状态是否合法由领域状态机校验，创建、更新和查询由应用层用例编排。
"""

import enum
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, Relationship

from app.core.database import SQLModelBase

if TYPE_CHECKING:
    from app.modules.user.model.user import User


class VideoTaskStatus(str, enum.Enum):
    """平台视频任务的状态集合，终态不可再回到处理态。"""

    submitting = "submitting"
    submission_unknown = "submission_unknown"
    queued = "queued"
    processing = "processing"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"
    timed_out = "timed_out"


RESULT_DELIVERY_KEY = "result_delivery"
"""``VideoTask.execution_snapshot`` 中记录成品交付方式的键名。"""

RESULT_DELIVERY_EXTERNAL = "external"
"""成品交付方式取值：上游直链直接交付客户端，平台不再下载并本地化成品。"""


class VideoTask(SQLModelBase, table=True):
    """保存用户视频请求、计费配置快照和任务当前状态。

    该实体关联任务所有者、阶段执行及追加式审计事件；请求快照不得包含 Provider 认证密钥，
    已创建任务始终使用冻结的配置版本，后续配置变更不影响其计费和追溯。
    """

    __tablename__ = "video_tasks"
    __table_args__ = (Index("ix_video_tasks_status_created_at", "status", "created_at"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True, description="应用侧生成的视频任务主键")
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True), nullable=False, server_default=func.now(), comment="任务首次创建时间"
        ),
    )
    user_id: UUID = Field(
        sa_column=Column(
            ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
            comment="创建任务的用户，禁止删除仍有关联任务的用户",
        )
    )
    model_id: UUID = Field(sa_column=Column(ForeignKey("models.id", ondelete="RESTRICT"), nullable=False, index=True))
    token_group_id: int = Field(
        sa_column=Column(ForeignKey("token_groups.id", ondelete="RESTRICT"), nullable=False, index=True)
    )
    status: VideoTaskStatus = Field(
        default=VideoTaskStatus.submitting,
        sa_column=Column(
            Enum(VideoTaskStatus, name="video_task_lifecycle_status"),
            nullable=False,
            index=True,
            comment="受领域状态机约束的任务生命周期状态",
        ),
    )
    input_payload: dict = Field(sa_column=Column(JSONB, nullable=False, comment="用户原始请求的可审计快照"))
    normalized_input: dict = Field(sa_column=Column(JSONB, nullable=False, comment="模型投影和报价使用的标准化输入"))
    prompt: str | None = Field(default=None, sa_column=Column(String(4096), nullable=True))
    duration_seconds: int | None = Field(default=None, sa_column=Column(Integer, nullable=True))
    execution_snapshot: dict = Field(
        sa_column=Column(JSONB, nullable=False, comment="脱敏的能力、渠道、映射和上游请求快照")
    )
    pricing_snapshot: dict = Field(sa_column=Column(JSONB, nullable=False, comment="不可变的报价决策快照"))
    result_payload: dict | None = Field(default=None, sa_column=Column(JSONB, comment="上游成功响应的脱敏摘要"))
    upstream_task_id: str | None = Field(default=None, sa_column=Column(String(128), index=True))
    submission_response: dict | None = Field(default=None, sa_column=Column(JSONB))
    result_url: str | None = Field(default=None, sa_column=Column(String(2048)))
    local_result_path: str | None = Field(default=None, sa_column=Column(String(512), nullable=True))
    local_result_content_type: str | None = Field(default=None, sa_column=Column(String(255), nullable=True))
    local_result_size_bytes: int | None = Field(default=None, sa_column=Column(Integer, nullable=True))
    result_public_expires_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    result_download_failed_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    submitted_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    last_polled_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True),
            nullable=True,
            comment="最近一次向上游查询任务状态的时间，轮询任务与读请求共用同一时间戳",
        ),
    )
    error_payload: dict | None = Field(
        default=None, sa_column=Column(JSONB, comment="任务失败、超时或下载异常的结构化原因")
    )
    progress: int = Field(
        default=0, sa_column=Column(Integer, nullable=False, comment="由上游轮询同步的任务进度百分比")
    )
    completed_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), comment="进入成功、失败、取消或超时终态的时间")
    )
    user: "User" = Relationship(back_populates="video_tasks")
    events: list["TaskEvent"] = Relationship(back_populates="task")


class TaskEvent(SQLModelBase, table=True):
    """追加式任务审计事件，记录状态机已接受的转移和其原因。

    事件不可用于反向推导或修改任务状态，只为排障、审计和恢复任务处理过程提供历史依据。
    """

    __tablename__ = "task_events"

    id: UUID = Field(default_factory=uuid4, primary_key=True, description="任务审计事件主键")
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True), nullable=False, server_default=func.now(), comment="审计事件创建时间"
        ),
    )
    task_id: UUID = Field(
        sa_column=Column(
            ForeignKey("video_tasks.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
            comment="关联任务，任务删除时审计事件随之删除",
        )
    )
    from_status: str | None = Field(
        default=None, sa_column=Column(String(32), comment="转移前状态，首次创建事件可为空")
    )
    to_status: str = Field(sa_column=Column(String(32), nullable=False, comment="经状态机校验后写入的目标状态"))
    event_type: str = Field(sa_column=Column(String(64), nullable=False, comment="描述状态转移业务原因的事件类型"))
    payload: dict = Field(
        default_factory=dict, sa_column=Column(JSONB, nullable=False, comment="事件关联的脱敏审计上下文")
    )
    task: "VideoTask" = Relationship(back_populates="events")
