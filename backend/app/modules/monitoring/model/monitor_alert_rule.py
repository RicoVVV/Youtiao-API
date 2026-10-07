"""分组监控告警阈值规则 ORM 模型。

``group_id`` 为空表示全局默认规则，非空表示该分组的覆盖规则；
阈值字段为空表示不评估该指标；``at_mobiles`` 为空表示沿用全局默认规则的 @ 目标。
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, Numeric, String, func, text
from sqlmodel import Field

from app.core.database import SQLModelBase


class MonitorAlertRule(SQLModelBase, table=True):
    """保存全局默认与按分组覆盖的告警阈值。"""

    __tablename__ = "monitor_alert_rules"
    __table_args__ = (
        Index(
            "uq_monitor_alert_rules_scope",
            text("COALESCE(group_id, 0)"),
            unique=True,
            postgresql_where=text("is_del = false"),
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True, description="规则主键")
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
            comment="覆盖分组标识，为空表示全局默认规则",
        ),
    )
    enabled: bool = Field(
        default=True, sa_column=Column(Boolean, nullable=False, server_default="true", comment="规则是否启用")
    )
    success_rate_min: Decimal | None = Field(
        default=None,
        sa_column=Column(Numeric(6, 4), nullable=True, comment="成功率下限，为空表示不评估成功率"),
    )
    avg_duration_ms_max: int | None = Field(
        default=None,
        sa_column=Column(Integer, nullable=True, comment="平均耗时上限（毫秒），为空表示不评估平均耗时"),
    )
    avg_first_token_ms_max: int | None = Field(
        default=None,
        sa_column=Column(Integer, nullable=True, comment="文本平均首 token 上限（毫秒），为空表示不评估该指标"),
    )
    min_sample_count: int = Field(
        default=20,
        sa_column=Column(Integer, nullable=False, server_default="20", comment="低于该样本数时跳过评估"),
    )
    consecutive_hits: int = Field(
        default=2,
        sa_column=Column(Integer, nullable=False, server_default="2", comment="连续命中多少个窗口才触发告警"),
    )
    at_mobiles: str = Field(
        default="",
        sa_column=Column(
            String(512), nullable=False, server_default="", comment="告警推送 @ 的手机号，逗号分隔，为空沿用全局规则"
        ),
    )
    at_all: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default="false", comment="告警推送是否 @ 所有人"),
    )
