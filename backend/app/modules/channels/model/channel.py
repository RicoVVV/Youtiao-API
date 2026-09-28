from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field

from app.core.database import SQLModelBase


class Channel(SQLModelBase, table=True):
    __tablename__ = "channels"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
    updated_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()),
    )
    name: str = Field(sa_column=Column(String(128), nullable=False))
    base_url: str = Field(sa_column=Column(String(512), nullable=False))
    api_key: str = Field(sa_column=Column(Text, nullable=False), exclude=True)
    config: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))
    supported_models: list[str] = Field(default_factory=list, sa_column=Column(JSONB, nullable=False))
    token_group_ids: list[int] = Field(default_factory=list, sa_column=Column(JSONB, nullable=False))
    model_mapping: dict[str, str] = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))
    param_override: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))
    header_override: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))
    latest_test_snapshot: dict[str, Any] | None = Field(default=None, sa_column=Column(JSONB, nullable=True))
    priority: int = Field(default=0, sa_column=Column(Integer, nullable=False))
    weight: int = Field(default=1, sa_column=Column(Integer, nullable=False))
    active: bool = Field(default=True, sa_column=Column(Boolean, nullable=False, index=True))
    healthy: bool = Field(default=True, sa_column=Column(Boolean, nullable=False, index=True))
