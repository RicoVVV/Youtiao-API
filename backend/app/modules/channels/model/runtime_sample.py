"""渠道运行时趋势采样 ORM 模型。

本模块只声明分钟级采样行；写入聚合、区间查询与超期清理由 ``channels.crud.samples`` 负责。
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, Numeric, String, func
from sqlmodel import Field

from app.core.database import SQLModelBase


class ChannelRuntimeSample(SQLModelBase, table=True):
    """保存一个渠道在某个分钟桶内的运行时状态快照。"""

    __tablename__ = "channel_runtime_samples"
    __table_args__ = (
        Index("uq_channel_runtime_samples_channel_bucket", "channel_id", "bucket_start", unique=True),
        Index("ix_channel_runtime_samples_bucket", "bucket_start"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True, description="采样主键")
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now(), comment="创建时间"),
    )
    channel_id: UUID = Field(
        sa_column=Column(ForeignKey("channels.id", ondelete="RESTRICT"), nullable=False, comment="渠道标识")
    )
    bucket_start: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, comment="分钟桶起点，UTC 对齐")
    )
    effective_weight: Decimal = Field(
        sa_column=Column(Numeric(10, 2), nullable=False, comment="渠道全部路由有效权重的算术平均")
    )
    success_rate: Decimal | None = Field(
        default=None, sa_column=Column(Numeric(5, 4), nullable=True, comment="渠道全部路由成功率算术平均")
    )
    average_latency_ms: int | None = Field(
        default=None, sa_column=Column(Integer, nullable=True, comment="渠道全部路由平均耗时，单位毫秒")
    )
    circuit_state: str = Field(
        sa_column=Column(String(16), nullable=False, comment="采样时的渠道熔断状态：closed/open/half_open")
    )
    active: bool = Field(sa_column=Column(Boolean, nullable=False, comment="采样时渠道是否启用"))
