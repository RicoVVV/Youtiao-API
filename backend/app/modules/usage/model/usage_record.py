"""跨能力 API 调用使用记录 ORM 模型。"""

import enum
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from app.core.database import SQLModelBase

if TYPE_CHECKING:
    from app.modules.user.model.user import User
from sqlalchemy import Column, DateTime, Enum, ForeignKey, Index, Integer, Numeric, String, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, Relationship


class UsageRecordStatus(str, enum.Enum):
    reserved = "reserved"
    succeeded = "succeeded"
    failed = "failed"
    refunded = "refunded"


class UsageRecord(SQLModelBase, table=True):
    __tablename__ = "usage_records"
    __table_args__ = (
        Index("ix_usage_records_user_created_at", "user_id", "created_at"),
        Index("ix_usage_records_resource", "resource_type", "resource_id"),
        Index("ix_usage_records_channel_created_at", "channel_id", "created_at"),
    )
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    created_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    )
    user_id: UUID = Field(sa_column=Column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True))
    access_token_id: UUID | None = Field(
        default=None, sa_column=Column(ForeignKey("tokens.id", ondelete="SET NULL"), index=True)
    )
    token_display_name: str | None = Field(default=None, sa_column=Column(String(128)))
    token_group_id: int | None = Field(
        default=None, sa_column=Column(ForeignKey("token_groups.id", ondelete="SET NULL"), index=True)
    )
    request_id: str = Field(sa_column=Column(String(128), nullable=False, index=True))
    request_type: str = Field(sa_column=Column(String(64), nullable=False, index=True))
    resource_type: str | None = Field(default=None, sa_column=Column(String(64)))
    resource_id: UUID | None = Field(default=None, sa_column=Column(Uuid, index=True))
    model_id: UUID | None = Field(
        default=None, sa_column=Column(ForeignKey("models.id", ondelete="SET NULL"), index=True)
    )
    model_name: str = Field(sa_column=Column(String(64), nullable=False, index=True))
    channel_id: UUID | None = Field(
        default=None, sa_column=Column(ForeignKey("channels.id", ondelete="SET NULL"), index=True)
    )
    channel_name: str | None = Field(default=None, sa_column=Column(String(128)))
    provider_name: str = Field(sa_column=Column(String(64), nullable=False))
    request_payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))
    response_metadata: dict[str, Any] | None = Field(default=None, sa_column=Column(JSONB))
    public_response_payload: dict[str, Any] | None = Field(default=None, sa_column=Column(JSONB))
    upstream_response_payload: dict[str, Any] | None = Field(default=None, sa_column=Column(JSONB))
    status: UsageRecordStatus = Field(
        default=UsageRecordStatus.reserved,
        sa_column=Column(Enum(UsageRecordStatus, name="usage_record_status"), nullable=False, index=True),
    )
    amount: Decimal = Field(sa_column=Column(Numeric(18, 6), nullable=False))
    started_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    )
    completed_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    duration_ms: int | None = Field(default=None, sa_column=Column(Integer))
    first_token_duration_ms: int | None = Field(default=None, sa_column=Column(Integer))
    prompt_tokens: int | None = Field(default=None, sa_column=Column(Integer))
    completion_tokens: int | None = Field(default=None, sa_column=Column(Integer))
    cached_tokens: int | None = Field(default=None, sa_column=Column(Integer))
    cache_write_tokens: int | None = Field(default=None, sa_column=Column(Integer))
    user: "User" = Relationship()
