"""服务器资源监控快照 ORM 模型。

一行代表宿主整机在一个 1 分钟窗口内的资源采样结果：
CPU、内存、负载等标量指标独立成列以便聚合与取趋势，
每核使用率、网卡流量与挂载点容量等多值维度以 JSONB 整体保存。
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, Column, DateTime, Index, Integer, Numeric, String, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field

from app.core.database import SQLModelBase


class ServerMetricSnapshot(SQLModelBase, table=True):
    """保存宿主整机在单个 1 分钟窗口内的资源采样值。

    速率类指标（CPU 使用率、网卡收发速率）由相邻两行的原始计数器差值计算，
    因此行内同时保存累计量，缺失上一行时速率类字段为空。
    """

    __tablename__ = "server_metric_snapshots"
    __table_args__ = (Index("uq_server_metric_snapshots_window", "window_start", unique=True),)

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
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True, comment="1 分钟窗口起点，UTC 对齐")
    )
    sample_interval_seconds: Decimal | None = Field(
        default=None,
        sa_column=Column(Numeric(12, 3), nullable=True, comment="与上一行的实际采样间隔秒数，用于换算速率"),
    )
    cpu_usage_percent: Decimal | None = Field(
        default=None, sa_column=Column(Numeric(7, 3), nullable=True, comment="整机 CPU 使用率，缺失上一行时为空")
    )
    cpu_total_seconds: Decimal | None = Field(
        default=None,
        sa_column=Column(Numeric(20, 3), nullable=True, comment="CPU 累计总时间，供下一行做差值"),
    )
    cpu_idle_seconds: Decimal | None = Field(
        default=None,
        sa_column=Column(Numeric(20, 3), nullable=True, comment="CPU 累计空闲时间，供下一行做差值"),
    )
    cpu_core_count: int = Field(default=0, sa_column=Column(Integer, nullable=False, comment="逻辑核数"))
    cpu_per_core_percent: list | None = Field(
        default=None,
        sa_column=Column(JSONB, nullable=True, comment="每核使用率数组，缺失上一行时为空"),
    )
    cpu_per_core_counters: list | None = Field(
        default=None,
        sa_column=Column(JSONB, nullable=True, comment="每核累计总时间与空闲时间数组，供下一行做差值"),
    )
    load1: Decimal | None = Field(default=None, sa_column=Column(Numeric(12, 3), nullable=True, comment="1 分钟负载"))
    load5: Decimal | None = Field(default=None, sa_column=Column(Numeric(12, 3), nullable=True, comment="5 分钟负载"))
    load15: Decimal | None = Field(default=None, sa_column=Column(Numeric(12, 3), nullable=True, comment="15 分钟负载"))
    memory_total_bytes: int | None = Field(
        default=None, sa_column=Column(BigInteger, nullable=True, comment="物理内存总量，单位字节")
    )
    memory_used_bytes: int | None = Field(
        default=None, sa_column=Column(BigInteger, nullable=True, comment="物理内存已用量，单位字节")
    )
    memory_usage_percent: Decimal | None = Field(
        default=None,
        sa_column=Column(Numeric(7, 3), nullable=True, comment="物理内存使用率，按 1 - 可用率 计算"),
    )
    swap_total_bytes: int | None = Field(
        default=None, sa_column=Column(BigInteger, nullable=True, comment="交换分区总量，单位字节")
    )
    swap_used_bytes: int | None = Field(
        default=None, sa_column=Column(BigInteger, nullable=True, comment="交换分区已用量，单位字节")
    )
    swap_usage_percent: Decimal | None = Field(
        default=None, sa_column=Column(Numeric(7, 3), nullable=True, comment="交换分区使用率")
    )
    network_interfaces: list = Field(
        default_factory=list,
        sa_column=Column(
            JSONB,
            nullable=False,
            server_default=text("'[]'::jsonb"),
            comment="各网卡收发累计量、速率与错误包数量",
        ),
    )
    disks: list = Field(
        default_factory=list,
        sa_column=Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"), comment="各挂载点容量与使用率明细"),
    )
    max_disk_usage_percent: Decimal | None = Field(
        default=None,
        sa_column=Column(Numeric(7, 3), nullable=True, comment="最满挂载点使用率，供磁盘告警直接判定"),
    )
    max_disk_mount: str | None = Field(
        default=None, sa_column=Column(String(512), nullable=True, comment="最满挂载点路径，供告警文案展示")
    )
