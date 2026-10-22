"""余额预警状态模型，记录用户本轮低余额提醒是否已发送。"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Column, DateTime, ForeignKey, Numeric, func
from sqlmodel import Field

from app.core.database import SQLModelBase


class BalanceAlertState(SQLModelBase, table=True):
    """每个用户至多一条余额预警状态。

    记录最近一次提醒时间，用于同一低余额周期内的去重；余额重新跌破阈值时按跨阈值事件再次提醒。
    """

    __tablename__ = "balance_alert_states"

    user_id: UUID = Field(
        sa_column=Column(
            ForeignKey("users.id", ondelete="RESTRICT"),
            primary_key=True,
            comment="预警状态所属用户",
        )
    )
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
    updated_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
            onupdate=func.now(),
            comment="最近一次状态变更时间",
        ),
    )
    alerted_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True, comment="本轮低余额提醒邮件的发送时间"),
    )
    balance_at_alert: Decimal | None = Field(
        default=None,
        sa_column=Column(Numeric(18, 6), nullable=True, comment="发送提醒邮件时的账户余额"),
    )
