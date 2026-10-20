from typing import Literal

from pydantic import AnyHttpUrl, BaseModel, Field, TypeAdapter, field_validator

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
    smtp_host: str
    smtp_port: int
    smtp_security: str
    smtp_username: str
    smtp_password_configured: bool
    smtp_from_email: str
    smtp_from_name: str


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

    @field_validator("server_url", "logo_url", mode="before")
    @classmethod
    def normalize_url(cls, value: str | None) -> str | None:
        if value is None or not str(value).strip():
            return ""
        return str(TypeAdapter(AnyHttpUrl).validate_python(value))


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
