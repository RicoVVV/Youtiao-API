from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from app.core.database import SQLModelBase
from sqlalchemy import Column, Date, DateTime, Index, Integer, Numeric, String, func
from sqlmodel import Field


class UsageDailyStatistic(SQLModelBase, table=True):
    __tablename__ = "usage_daily_statistics"
    __table_args__ = (
        Index("ix_usage_daily_statistics_date_user", "stat_date", "user_id"),
        Index("ix_usage_daily_statistics_date_model", "stat_date", "model_name"),
        Index("ix_usage_daily_statistics_date_channel", "stat_date", "channel_name"),
        Index("ix_usage_daily_statistics_date_provider", "stat_date", "provider_name"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    stat_date: date = Field(sa_column=Column(Date, nullable=False, index=True))
    user_id: UUID = Field(nullable=False, index=True)
    access_token_id: UUID | None = Field(default=None, index=True)
    token_display_name: str | None = Field(default=None, sa_column=Column(String(128)))
    request_type: str = Field(sa_column=Column(String(64), nullable=False, index=True))
    model_id: UUID | None = Field(default=None, index=True)
    model_name: str = Field(sa_column=Column(String(64), nullable=False))
    channel_id: UUID | None = Field(default=None, index=True)
    channel_name: str | None = Field(default=None, sa_column=Column(String(128)))
    provider_name: str = Field(sa_column=Column(String(64), nullable=False))
    succeeded_count: int = Field(default=0, sa_column=Column(Integer, nullable=False))
    refunded_count: int = Field(default=0, sa_column=Column(Integer, nullable=False))
    settled_amount: Decimal = Field(default=Decimal("0"), sa_column=Column(Numeric(18, 6), nullable=False))
    total_duration_ms: int = Field(default=0, sa_column=Column(Integer, nullable=False))
    updated_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()),
    )
