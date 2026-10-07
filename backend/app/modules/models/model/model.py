from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field

from app.core.database import SQLModelBase


class Model(SQLModelBase, table=True):
    __tablename__ = "models"
    __table_args__ = (Index("uq_models_name_active", "name", unique=True, postgresql_where=text("is_del = false")),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
    updated_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()),
    )
    name: str = Field(sa_column=Column(String(64), nullable=False))
    description: str | None = Field(default=None, sa_column=Column(String(512), nullable=True))
    model_type: str = Field(sa_column=Column(String(32), nullable=False, index=True))
    template_id: str | None = Field(default=None, sa_column=Column(String(128), nullable=True, index=True))
    input_contract: dict[str, Any] | None = Field(default=None, sa_column=Column(JSONB, nullable=True))
    pricing_fields: list[str] = Field(
        default_factory=list, sa_column=Column(JSONB, nullable=False, server_default="[]")
    )
    default_concurrency_limit: int | None = Field(
        default=None,
        sa_column=Column(Integer, CheckConstraint("default_concurrency_limit BETWEEN 0 AND 10000"), nullable=True),
    )
    active: bool = Field(default=True, sa_column=Column(Boolean, nullable=False, index=True))


class ModelRoute(SQLModelBase, table=True):
    __tablename__ = "model_routes"
    __table_args__ = (
        CheckConstraint("weight > 0", name="ck_model_routes_weight_positive"),
        Index(
            "uq_model_routes_model_group_channel_active",
            "model_id",
            "token_group_id",
            "channel_id",
            unique=True,
            postgresql_where=text("is_del = false"),
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
    updated_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()),
    )
    model_id: UUID = Field(sa_column=Column(ForeignKey("models.id", ondelete="RESTRICT"), nullable=False, index=True))
    token_group_id: int = Field(
        sa_column=Column(ForeignKey("token_groups.id", ondelete="RESTRICT"), nullable=False, index=True)
    )
    channel_id: UUID = Field(
        sa_column=Column(ForeignKey("channels.id", ondelete="RESTRICT"), nullable=False, index=True)
    )
    priority: int = Field(default=0, sa_column=Column(Integer, nullable=False))
    weight: int = Field(default=1, sa_column=Column(Integer, nullable=False))
    enabled: bool = Field(default=True, sa_column=Column(Boolean, nullable=False, index=True))
    healthy: bool = Field(default=True, sa_column=Column(Boolean, nullable=False, index=True))
