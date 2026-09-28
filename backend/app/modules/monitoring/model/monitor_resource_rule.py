"""服务器资源告警阈值规则 ORM 模型，单行保存整机资源阈值。

资源告警只有一个评估目标（服务器本身），不存在分组维度，
因此与推送配置同样使用固定主键的单行表，避免与分组规则表混用。
阈值为空表示不评估该指标。
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Boolean, Column, DateTime, Integer, Numeric, func
from sqlmodel import Field

from app.core.database import SQLModelBase

MONITOR_RESOURCE_RULE_ID = UUID(int=2)
"""资源阈值规则固定使用的主键，保证配置表始终只有一行。"""


class MonitorResourceRule(SQLModelBase, table=True):
    """保存服务器资源告警的启用开关、各项阈值与连续命中要求。"""

    __tablename__ = "monitor_resource_rules"

    id: UUID = Field(default=MONITOR_RESOURCE_RULE_ID, primary_key=True, description="配置主键，固定值")
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
    enabled: bool = Field(
        default=True, sa_column=Column(Boolean, nullable=False, server_default="true", comment="是否评估资源告警")
    )
    cpu_usage_max: Decimal | None = Field(
        default=None, sa_column=Column(Numeric(7, 3), nullable=True, comment="CPU 使用率上限，为空表示不评估")
    )
    memory_usage_max: Decimal | None = Field(
        default=None, sa_column=Column(Numeric(7, 3), nullable=True, comment="内存使用率上限，为空表示不评估")
    )
    swap_usage_max: Decimal | None = Field(
        default=None, sa_column=Column(Numeric(7, 3), nullable=True, comment="交换分区使用率上限，为空表示不评估")
    )
    disk_usage_max: Decimal | None = Field(
        default=None, sa_column=Column(Numeric(7, 3), nullable=True, comment="最满挂载点使用率上限，为空表示不评估")
    )
    consecutive_hits: int = Field(
        default=3,
        sa_column=Column(Integer, nullable=False, server_default="3", comment="连续命中多少个采样窗口才触发告警"),
    )
