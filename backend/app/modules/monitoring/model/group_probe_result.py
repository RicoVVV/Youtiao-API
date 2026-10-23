"""分组文本嗅探结果 ORM 模型。

嗅探模式由平台主动向分组发送最小文本请求，结果只用于监控展示，
不写入使用记录、不产生扣费，也不参与渠道熔断与自动禁用。
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, func
from sqlmodel import Field

from app.core.database import SQLModelBase


class GroupProbeResult(SQLModelBase, table=True):
    """保存一次分组文本嗅探的渠道、模型、状态与耗时。"""

    __tablename__ = "group_probe_results"
    __table_args__ = (Index("ix_group_probe_results_group_completed", "token_group_id", "completed_at"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True, description="嗅探结果主键")
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now(), comment="创建时间"),
    )
    completed_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True, comment="嗅探完成时间，UTC")
    )
    token_group_id: int = Field(
        sa_column=Column(
            ForeignKey("token_groups.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
            comment="嗅探所属 Token 分组标识",
        )
    )
    model_id: UUID | None = Field(
        default=None,
        sa_column=Column(ForeignKey("models.id", ondelete="SET NULL"), nullable=True, index=True),
    )
    model_name: str = Field(sa_column=Column(String(64), nullable=False, comment="本次嗅探使用的公开模型名称"))
    channel_id: UUID | None = Field(
        default=None,
        sa_column=Column(ForeignKey("channels.id", ondelete="SET NULL"), nullable=True, index=True),
    )
    channel_name: str | None = Field(default=None, sa_column=Column(String(128), comment="本次嗅探使用的渠道名称"))
    provider_name: str = Field(sa_column=Column(String(64), nullable=False, comment="Provider 类型"))
    request_type: str = Field(
        default="text",
        sa_column=Column(String(64), nullable=False, server_default="text", comment="嗅探请求类型，固定为 text"),
    )
    status: str = Field(sa_column=Column(String(32), nullable=False, comment="嗅探结果：succeeded 或 failed"))
    duration_ms: int = Field(sa_column=Column(Integer, nullable=False, comment="嗅探请求耗时，单位毫秒"))
    first_token_duration_ms: int | None = Field(
        default=None, sa_column=Column(Integer, comment="首 token 耗时；非流式嗅探成功时等于总耗时")
    )
    error_code: str | None = Field(default=None, sa_column=Column(String(64), comment="失败错误码"))
    error_message: str | None = Field(default=None, sa_column=Column(String(512), comment="失败错误摘要"))
