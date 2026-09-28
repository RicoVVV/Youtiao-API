"""分组监控告警记录 ORM 模型。

一行代表一个「分组 × 渠道（可为空）× 指标」的告警事件，状态在其中流转；
渠道为空表示分组级告警，非空表示渠道级告警。
``group_id`` 为空表示服务器资源告警，此类告警没有分组与渠道维度。
"""

import enum
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Index, Integer, Numeric, String, func, text
from sqlmodel import Field

from app.core.database import SQLModelBase


class MonitorAlertStatus(str, enum.Enum):
    """告警事件的活跃状态。"""

    pending = "pending"
    open = "open"
    resolved = "resolved"
    acknowledged = "acknowledged"
    ignored = "ignored"


class MonitorAlertMetric(str, enum.Enum):
    """告警覆盖的指标类别。"""

    success_rate = "success_rate"
    average_duration_ms = "average_duration_ms"
    average_first_token_ms = "average_first_token_ms"
    cpu_usage = "cpu_usage"
    memory_usage = "memory_usage"
    swap_usage = "swap_usage"
    disk_usage = "disk_usage"


RESOURCE_ALERT_METRICS = (
    MonitorAlertMetric.cpu_usage,
    MonitorAlertMetric.memory_usage,
    MonitorAlertMetric.swap_usage,
    MonitorAlertMetric.disk_usage,
)
"""服务器资源类指标，其告警的分组标识为空。"""


class MonitorAlertNotificationStatus(str, enum.Enum):
    """告警记录的推送结果。"""

    pending = "pending"
    sent = "sent"
    failed = "failed"
    skipped = "skipped"


class MonitorAlert(SQLModelBase, table=True):
    """保存一次告警事件的阈值命中、状态流转与推送结果。"""

    __tablename__ = "monitor_alerts"
    __table_args__ = (
        Index(
            "uq_monitor_alerts_active",
            text("COALESCE(group_id, 0)"),
            text("COALESCE(channel_id, '00000000-0000-0000-0000-000000000000'::uuid)"),
            text("metric"),
            unique=True,
            postgresql_where=text("status IN ('pending', 'open') AND is_del = false"),
        ),
        Index(
            "ix_monitor_alerts_scope",
            text("COALESCE(group_id, 0)"),
            "channel_id",
            "metric",
            "status",
        ),
        Index("ix_monitor_alerts_status_updated", "status", "updated_at"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True, description="告警主键")
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
    group_id: int | None = Field(
        default=None,
        sa_column=Column(
            ForeignKey("token_groups.id", ondelete="RESTRICT"),
            nullable=True,
            index=True,
            comment="告警所属 Token 分组标识，为空表示服务器资源告警",
        ),
    )
    channel_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            ForeignKey("channels.id", ondelete="RESTRICT"),
            nullable=True,
            index=True,
            comment="渠道级告警的渠道标识，为空表示分组级告警",
        ),
    )
    metric: MonitorAlertMetric = Field(
        sa_column=Column(
            Enum(MonitorAlertMetric, name="monitor_alert_metric"), nullable=False, comment="命中的指标类别"
        )
    )
    status: MonitorAlertStatus = Field(
        default=MonitorAlertStatus.pending,
        sa_column=Column(
            Enum(MonitorAlertStatus, name="monitor_alert_status"),
            nullable=False,
            index=True,
            comment="告警当前状态",
        ),
    )
    first_window_start: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, comment="首次命中该指标的窗口起点")
    )
    last_window_start: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, comment="最近一次评估命中的窗口起点")
    )
    triggered_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True, comment="转为已触发状态的时间")
    )
    resolved_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True, comment="指标恢复的时间")
    )
    acknowledged_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True, comment="人工确认或忽略的时间")
    )
    sample_count: int = Field(
        default=0, sa_column=Column(Integer, nullable=False, comment="最近一次评估窗口内的样本数")
    )
    actual_value: Decimal = Field(
        default=Decimal("0"),
        sa_column=Column(Numeric(18, 6), nullable=False, comment="最近一次评估窗口内的指标实际值"),
    )
    threshold_value: Decimal = Field(
        default=Decimal("0"),
        sa_column=Column(Numeric(18, 6), nullable=False, comment="命中时使用的阈值"),
    )
    consecutive_hits: int = Field(default=0, sa_column=Column(Integer, nullable=False, comment="连续命中窗口数"))
    notified_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True, comment="最近一次推送时间")
    )
    notification_status: MonitorAlertNotificationStatus = Field(
        default=MonitorAlertNotificationStatus.pending,
        sa_column=Column(
            Enum(MonitorAlertNotificationStatus, name="monitor_alert_notification_status"),
            nullable=False,
            comment="最近一次推送结果",
        ),
    )
    notification_error: str | None = Field(
        default=None, sa_column=Column(String(512), nullable=True, comment="最近一次推送失败原因")
    )
