from datetime import datetime
from uuid import UUID

from sqlalchemy import Column, DateTime, func
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
