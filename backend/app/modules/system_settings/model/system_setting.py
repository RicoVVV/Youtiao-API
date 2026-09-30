from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, func
from sqlmodel import Field

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
