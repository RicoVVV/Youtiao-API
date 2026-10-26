from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, Column, DateTime, Integer, Numeric, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field

from app.core.channel_automation import (
    DEFAULT_AUTO_DISABLE_KEYWORDS,
    DEFAULT_AUTO_DISABLE_STATUS_CODES,
    DEFAULT_AUTO_RETRY_STATUS_CODES,
)
from app.core.database import SQLModelBase

SYSTEM_SETTINGS_ID = UUID(int=0)


class SystemSetting(SQLModelBase, table=True):
    __tablename__ = "system_settings"

    id: UUID = Field(default=SYSTEM_SETTINGS_ID, primary_key=True)
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
    updated_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()),
    )
    system_name: str = Field(default="", max_length=255)
    server_url: str = Field(default="", max_length=2048)
    logo_url: str = Field(default="", max_length=2048)
    footer_text: str = Field(default="", max_length=2000)
    about_content: str = Field(default="")
    homepage_content: str = Field(default="")
    terms_of_service: str = Field(default="")
    privacy_policy: str = Field(default="")
    email_verification_enabled: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default="false"),
    )
    smtp_host: str = Field(default="", sa_column=Column(String(255), nullable=False, server_default=""))
    smtp_port: int = Field(default=587, sa_column=Column(Integer, nullable=False, server_default="587"))
    smtp_security: str = Field(
        default="starttls", sa_column=Column(String(16), nullable=False, server_default="starttls")
    )
    smtp_username: str = Field(default="", sa_column=Column(String(320), nullable=False, server_default=""))
    smtp_password_ciphertext: str = Field(default="", sa_column=Column(Text(), nullable=False, server_default=""))
    smtp_from_email: str = Field(default="", sa_column=Column(String(320), nullable=False, server_default=""))
    smtp_from_name: str = Field(default="", sa_column=Column(String(255), nullable=False, server_default=""))
    balance_alert_enabled: bool = Field(
        default=False,
        sa_column=Column(
            Boolean,
            nullable=False,
            server_default="false",
            comment="是否启用用户余额预警邮件，依赖邮箱注册验证提供用户邮箱",
        ),
    )
    channel_probe_enabled: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default="false", comment="是否定时探测所有渠道"),
    )
    channel_probe_interval_minutes: int = Field(
        default=1,
        sa_column=Column(Integer, nullable=False, server_default="1", comment="定时探测所有渠道的间隔分钟数"),
    )
    channel_probe_timeout_seconds: int = Field(
        default=5,
        sa_column=Column(Integer, nullable=False, server_default="5", comment="单次渠道探测的最长响应秒数"),
    )
    channel_auto_disable_enabled: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default="false", comment="失败时是否自动禁用渠道"),
    )
    channel_auto_enable_enabled: bool = Field(
        default=True,
        sa_column=Column(Boolean, nullable=False, server_default="true", comment="成功后是否自动启用渠道"),
    )
    channel_auto_disable_status_codes: str = Field(
        default=DEFAULT_AUTO_DISABLE_STATUS_CODES,
        sa_column=Column(
            Text,
            nullable=False,
            server_default=DEFAULT_AUTO_DISABLE_STATUS_CODES,
            comment="触发自动禁用的上游状态码，逗号分隔，支持起止范围",
        ),
    )
    channel_auto_retry_status_codes: str = Field(
        default=DEFAULT_AUTO_RETRY_STATUS_CODES,
        sa_column=Column(
            Text,
            nullable=False,
            server_default=DEFAULT_AUTO_RETRY_STATUS_CODES,
            comment="允许自动重试的上游状态码，逗号分隔，支持起止范围；504 与 524 始终不重试",
        ),
    )
    channel_auto_disable_keywords: str = Field(
        default=DEFAULT_AUTO_DISABLE_KEYWORDS,
        sa_column=Column(
            Text,
            nullable=False,
            server_default=DEFAULT_AUTO_DISABLE_KEYWORDS,
            comment="触发自动禁用的上游错误关键词，换行分隔，不区分大小写",
        ),
    )
    sidebar_visibility: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(
            JSONB,
            nullable=False,
            server_default=text("'{}'::jsonb"),
            comment="控制台侧边栏分组与模块可见性覆盖，缺失键视为可见",
        ),
    )
    affiliate_enabled: bool = Field(
        default=False,
        sa_column=Column(
            Boolean,
            nullable=False,
            server_default="false",
            comment="是否启用邀请返利功能，公开给注册页决定是否展示邀请码输入",
        ),
    )
    affiliate_rebate_rate_percent: Decimal = Field(
        default=Decimal("5.00"),
        sa_column=Column(
            Numeric(5, 2),
            nullable=False,
            server_default="5.00",
            comment="全局邀请返利比例（百分比 0-100）",
        ),
    )
    affiliate_rebate_freeze_hours: int = Field(
        default=5,
        sa_column=Column(
            Integer,
            nullable=False,
            server_default="5",
            comment="邀请返利冻结小时数，0 表示不冻结",
        ),
    )
    affiliate_rebate_duration_days: int = Field(
        default=0,
        sa_column=Column(
            Integer,
            nullable=False,
            server_default="0",
            comment="被邀请人注册后产生返利的有效天数，0 表示永久有效",
        ),
    )
    affiliate_rebate_per_invitee_cap: Decimal = Field(
        default=Decimal("0"),
        sa_column=Column(
            Numeric(18, 6),
            nullable=False,
            server_default="0",
            comment="单个被邀请人可产生的返利上限（USD），0 表示无上限",
        ),
    )
    affiliate_signup_bonus: Decimal = Field(
        default=Decimal("0"),
        sa_column=Column(
            Numeric(18, 6),
            nullable=False,
            server_default="0",
            comment="通过邀请码或邀请链接注册的新用户赠送余额（USD），0 表示不赠送",
        ),
    )
