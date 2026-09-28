"""告警推送配置 ORM 模型，单行保存钉钉自定义机器人参数。"""

import enum
from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, Column, DateTime, Integer, String, func
from sqlmodel import Field

from app.core.database import SQLModelBase

MONITOR_NOTIFICATION_ID = UUID(int=1)
"""推送配置固定使用的主键，保证配置表始终只有一行。"""


class NotificationScope(str, enum.Enum):
    """推送配置对应的告警范围，与告警查询接口的 ``scope`` 取值保持一致。"""

    group = "group"
    server = "server"


class MonitorNotification(SQLModelBase, table=True):
    """保存钉钉机器人推送开关、地址与限流参数。"""

    __tablename__ = "monitor_notification"

    id: UUID = Field(default=MONITOR_NOTIFICATION_ID, primary_key=True, description="配置主键，固定值")
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
    notify_group_alerts: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default="false", comment="是否推送分组业务告警"),
    )
    notify_resource_alerts: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default="false", comment="是否推送服务器资源告警"),
    )
    webhook_url: str = Field(
        default="",
        sa_column=Column(String(2048), nullable=False, server_default="", comment="钉钉机器人 webhook 完整地址"),
    )
    sign_secret: str = Field(
        default="",
        sa_column=Column(String(512), nullable=False, server_default="", comment="钉钉加签密钥，为空表示未开启加签"),
    )
    keyword: str = Field(
        default="",
        sa_column=Column(String(64), nullable=False, server_default="", comment="机器人自定义关键词，作为推送标题前缀"),
    )
    timeout_seconds: int = Field(
        default=10,
        sa_column=Column(Integer, nullable=False, server_default="10", comment="单次推送请求超时秒数"),
    )
    silence_minutes: int = Field(
        default=30,
        sa_column=Column(Integer, nullable=False, server_default="30", comment="同一告警重复推送的最小间隔分钟数"),
    )
    notify_on_resolved: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default="false", comment="告警恢复时是否推送通知"),
    )
