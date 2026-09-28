"""分组级监控快照 ORM 模型。

本模块只声明 5 分钟窗口内某个 Token 分组的请求计数与耗时累计结构；
指标计算、窗口聚合写入与告警判定分别由应用层负责。
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Index, Integer, String, func
from sqlmodel import Field

from app.core.database import SQLModelBase


class GroupMetricSnapshot(SQLModelBase, table=True):
    """保存一个 5 分钟窗口内某个 Token 分组按请求类型聚合的原始计数。

    行按 ``window_start`` 对齐到 5 分钟边界，按 ``completed_at`` 归属窗口；
    成功率、平均耗时与平均首 token 均由这些计数派生，不额外存储派生值。
    """

    __tablename__ = "group_metric_snapshots"
    __table_args__ = (
        Index(
            "uq_group_metric_snapshots_window_group_type",
            "window_start",
            "token_group_id",
            "request_type",
            unique=True,
        ),
        Index("ix_group_metric_snapshots_group_window", "token_group_id", "window_start"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True, description="快照主键")
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now(), comment="创建时间"),
    )
    updated_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(), comment="更新时间"
        ),
    )
    window_start: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True, comment="5 分钟窗口起点，UTC 对齐")
    )
    token_group_id: int = Field(
        sa_column=Column(
            ForeignKey("token_groups.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
            comment="统计所属 Token 分组标识",
        )
    )
    request_type: str = Field(sa_column=Column(String(64), nullable=False, comment="请求类型：text、image 或 video"))
    succeeded_count: int = Field(default=0, sa_column=Column(Integer, nullable=False, comment="窗口内成功请求数"))
    failed_count: int = Field(default=0, sa_column=Column(Integer, nullable=False, comment="窗口内失败请求数"))
    refunded_count: int = Field(default=0, sa_column=Column(Integer, nullable=False, comment="窗口内退款请求数"))
    total_duration_ms: int = Field(
        default=0, sa_column=Column(BigInteger, nullable=False, comment="窗口内成功请求耗时之和，单位毫秒")
    )
    first_token_sum_ms: int = Field(
        default=0,
        sa_column=Column(BigInteger, nullable=False, comment="窗口内成功且有首 token 的请求耗时之和，单位毫秒"),
    )
    first_token_count: int = Field(
        default=0, sa_column=Column(Integer, nullable=False, comment="窗口内成功且记录到首 token 的请求数")
    )
