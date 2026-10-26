from decimal import Decimal
from typing import Literal

from pydantic import AnyHttpUrl, BaseModel, Field, TypeAdapter, field_validator

from app.core.affiliate import MAX_SIGNUP_BONUS
from app.core.channel_automation import parse_status_code_spec
from app.modules.system_settings.application.services import KEEP_PASSWORD_SENTINEL


class SystemSettingsResponse(BaseModel):
    system_name: str
    server_url: str
    logo_url: str
    footer_text: str
    about_content: str
    homepage_content: str
    terms_of_service: str
    privacy_policy: str
    email_verification_enabled: bool
    affiliate_enabled: bool
    affiliate_signup_bonus: Decimal


class AdminSystemSettingsResponse(BaseModel):
    """管理员系统设置响应，SMTP 密码仅返回是否已配置，不返回明文或密文。"""

    system_name: str
    server_url: str
    logo_url: str
    footer_text: str
    about_content: str
    homepage_content: str
    terms_of_service: str
    privacy_policy: str
    email_verification_enabled: bool
    affiliate_enabled: bool
    affiliate_signup_bonus: Decimal
    smtp_host: str
    smtp_port: int
    smtp_security: str
    smtp_username: str
    smtp_password_configured: bool
    smtp_from_email: str
    smtp_from_name: str
    balance_alert_enabled: bool
    channel_probe_enabled: bool
    channel_probe_interval_minutes: int
    channel_probe_timeout_seconds: int
    channel_auto_disable_enabled: bool
    channel_auto_enable_enabled: bool
    channel_auto_disable_status_codes: str
    channel_auto_retry_status_codes: str
    channel_auto_disable_keywords: str
    affiliate_rebate_rate_percent: Decimal
    affiliate_rebate_freeze_hours: int
    affiliate_rebate_duration_days: int
    affiliate_rebate_per_invitee_cap: Decimal


class SystemSettingsUpdateRequest(BaseModel):
    system_name: str | None = Field(default=None, max_length=255)
    server_url: str | None = Field(default=None, max_length=2048)
    logo_url: str | None = Field(default=None, max_length=2048)
    footer_text: str | None = Field(default=None, max_length=2000)
    about_content: str | None = None
    homepage_content: str | None = None
    terms_of_service: str | None = None
    privacy_policy: str | None = None
    email_verification_enabled: bool | None = None
    affiliate_enabled: bool | None = Field(default=None, description="是否启用邀请返利功能")
    affiliate_rebate_rate_percent: Decimal | None = Field(
        default=None, ge=0, le=100, description="全局邀请返利比例（百分比 0-100）"
    )
    affiliate_rebate_freeze_hours: int | None = Field(default=None, ge=0, le=720, description="返利冻结小时数")
    affiliate_rebate_duration_days: int | None = Field(default=None, ge=0, le=3650, description="返利有效天数")
    affiliate_rebate_per_invitee_cap: Decimal | None = Field(
        default=None, ge=0, description="单个被邀请人的返利上限（USD），0 表示无上限"
    )
    affiliate_signup_bonus: Decimal | None = Field(
        default=None, ge=0, le=MAX_SIGNUP_BONUS, description="邀请码注册赠送余额（USD），0 表示不赠送"
    )
    smtp_host: str | None = Field(default=None, max_length=255)
    smtp_port: int | None = Field(default=None, ge=1, le=65535)
    smtp_security: Literal["none", "starttls", "ssl"] | None = None
    smtp_username: str | None = Field(default=None, max_length=320)
    smtp_password: str | None = Field(
        default=KEEP_PASSWORD_SENTINEL,
        max_length=1024,
        description="不传则保留原密码；传空字符串清空密码；传非空字符串加密后替换",
        repr=False,
    )
    smtp_from_email: str | None = Field(default=None, max_length=320)
    smtp_from_name: str | None = Field(default=None, max_length=255)
    balance_alert_enabled: bool | None = Field(
        default=None, description="开启后按用户设置的阈值发送余额提醒邮件，必须同时开启邮箱注册验证"
    )
    channel_probe_enabled: bool | None = Field(default=None, description="是否定时探测所有渠道")
    channel_probe_interval_minutes: int | None = Field(default=None, ge=1, le=1440, description="探测间隔分钟数")
    channel_probe_timeout_seconds: int | None = Field(default=None, ge=1, le=600, description="单次探测最长响应秒数")
    channel_auto_disable_enabled: bool | None = Field(default=None, description="失败时是否自动禁用渠道")
    channel_auto_enable_enabled: bool | None = Field(default=None, description="成功后是否自动启用渠道")
    channel_auto_disable_status_codes: str | None = Field(
        default=None, max_length=2048, description="触发自动禁用的状态码，逗号分隔，支持起止范围"
    )
    channel_auto_retry_status_codes: str | None = Field(
        default=None, max_length=2048, description="允许自动重试的状态码，逗号分隔，支持起止范围；504 与 524 始终不重试"
    )
    channel_auto_disable_keywords: str | None = Field(
        default=None, max_length=8192, description="触发自动禁用的错误关键词，换行分隔，不区分大小写"
    )

    @field_validator("server_url", "logo_url", mode="before")
    @classmethod
    def normalize_url(cls, value: str | None) -> str | None:
        if value is None or not str(value).strip():
            return ""
        return str(TypeAdapter(AnyHttpUrl).validate_python(value))

    @field_validator("channel_auto_disable_status_codes", "channel_auto_retry_status_codes")
    @classmethod
    def validate_status_codes(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            parse_status_code_spec(value)
        except ValueError as exc:
            raise ValueError("状态码必须是 100-599 之间的单个状态码或起止范围，使用逗号分隔") from exc
        return value.strip()


class SidebarModulesResponse(BaseModel):
    """公开侧边栏可见性响应，仅返回生效可见的模块 key。"""

    modules: list[str]


class SidebarGroupCatalogItem(BaseModel):
    key: str
    modules: list[str]


class SidebarCatalogResponse(BaseModel):
    groups: list[SidebarGroupCatalogItem]


class SidebarVisibilityResponse(BaseModel):
    groups: dict[str, bool]
    modules: dict[str, bool]


class AdminSidebarModulesResponse(BaseModel):
    """管理员侧边栏配置响应：目录 + 已补全默认值的完整开关表。"""

    catalog: SidebarCatalogResponse
    visibility: SidebarVisibilityResponse


class SidebarModulesUpdateRequest(BaseModel):
    """整体替换侧边栏可见性；两个字段均必填，空 map 表示该维度全部可见。"""

    groups: dict[str, bool] = Field(description="分组 key → 是否可见")
    modules: dict[str, bool] = Field(description="模块 key → 是否可见")
