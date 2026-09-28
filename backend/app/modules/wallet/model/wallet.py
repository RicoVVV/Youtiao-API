"""钱包、余额明细、使用记录和在线充值订单的 ORM 模型，为支付回调入账提供持久化载体。"""

import enum
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlmodel import Field, Relationship

from app.core.database import SQLModelBase

if TYPE_CHECKING:
    from app.modules.user.model.user import User


class BalanceRecordType(str, enum.Enum):
    recharge = "recharge"
    admin_grant = "admin_grant"
    redemption = "redemption"
    usage = "usage"
    refund = "refund"


class RechargeOrderStatus(str, enum.Enum):
    pending = "pending"
    paid = "paid"
    closed = "closed"
    refunded = "refunded"


class Wallet(SQLModelBase, table=True):
    """用户唯一可用余额载体。

    普通按次能力在调用前预扣，防止透支；文本按 token 后付费允许余额短暂为负，表示待补缴欠费。
    """

    __tablename__ = "wallets"

    id: UUID = Field(default_factory=uuid4, primary_key=True, description="应用侧生成的钱包主键")
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True), nullable=False, server_default=func.now(), comment="钱包首次创建时间"
        ),
    )
    user_id: UUID = Field(
        sa_column=Column(
            ForeignKey("users.id", ondelete="RESTRICT"),
            unique=True,
            nullable=False,
            comment="钱包所属用户，保留账务历史时禁止删除",
        )
    )
    balance: Decimal = Field(
        default=Decimal("0"),
        sa_column=Column(Numeric(18, 6), nullable=False, comment="当前可用人民币余额"),
    )
    updated_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
            onupdate=func.now(),
            comment="最近一次余额变动时间",
        ),
    )
    user: "User" = Relationship(back_populates="wallet")


class BalanceRecord(SQLModelBase, table=True):
    """每次余额变动的不可变审计明细。"""

    __tablename__ = "balance_records"
    __table_args__ = (
        CheckConstraint("change_amount <> 0", name="ck_balance_records_change_nonzero"),
        Index("ix_balance_records_user_created_at", "user_id", "created_at"),
    )
    id: UUID = Field(default_factory=uuid4, primary_key=True, description="不可变余额明细主键")
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True), nullable=False, server_default=func.now(), comment="余额变动入账时间"
        ),
    )
    user_id: UUID = Field(
        sa_column=Column(
            ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True, comment="余额所属用户"
        )
    )
    change_amount: Decimal = Field(
        sa_column=Column(Numeric(18, 6), nullable=False, comment="本次余额变动金额，正数入账、负数扣费")
    )
    balance_before: Decimal = Field(sa_column=Column(Numeric(18, 6), nullable=False, comment="变动前可用余额"))
    balance_after: Decimal = Field(sa_column=Column(Numeric(18, 6), nullable=False, comment="变动后可用余额"))
    record_type: BalanceRecordType = Field(
        sa_column=Column(
            Enum(BalanceRecordType, name="balance_record_type"), nullable=False, comment="余额变动业务类型"
        )
    )
    reason: str = Field(sa_column=Column(String(256), nullable=False, comment="余额变动原因"))
    operator_id: UUID | None = Field(
        default=None,
        sa_column=Column(ForeignKey("users.id", ondelete="RESTRICT"), comment="执行管理员；用户自助操作为空"),
    )
    usage_record_id: UUID | None = Field(
        default=None,
        sa_column=Column(ForeignKey("usage_records.id", ondelete="RESTRICT"), index=True, comment="关联的视频调用记录"),
    )
    recharge_order_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            ForeignKey("recharge_orders.id", ondelete="RESTRICT"), unique=True, comment="关联的在线充值订单"
        ),
    )
    redemption_code_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            ForeignKey("redemption_codes.id", ondelete="RESTRICT"), unique=True, comment="关联的兑换码核销记录"
        ),
    )


class RechargeOrder(SQLModelBase, table=True):
    """在线支付充值订单，不承载管理员授予或兑换码入账。"""

    __tablename__ = "recharge_orders"
    __table_args__ = (UniqueConstraint("order_no", name="uq_recharge_orders_order_no"),)
    id: UUID = Field(default_factory=uuid4, primary_key=True, description="充值订单主键")
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now(), comment="订单创建时间"),
    )
    user_id: UUID = Field(
        sa_column=Column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True, comment="充值用户")
    )
    order_no: str = Field(sa_column=Column(String(64), nullable=False, comment="业务充值订单号"))
    amount: Decimal = Field(sa_column=Column(Numeric(18, 6), nullable=False, comment="充值人民币金额"))
    payment_channel: str = Field(sa_column=Column(String(32), nullable=False, comment="支付渠道"))
    payment_method: str = Field(
        default="page_pay", sa_column=Column(String(32), nullable=False, server_default="page_pay", comment="支付方式")
    )
    expected_pay_amount: Decimal | None = Field(
        default=None, sa_column=Column(Numeric(18, 6), nullable=True, comment="服务端冻结的实际应付款金额")
    )
    channel_transaction_id: str | None = Field(
        default=None, sa_column=Column(String(128), unique=True, comment="支付渠道交易号")
    )
    status: RechargeOrderStatus = Field(
        default=RechargeOrderStatus.pending,
        sa_column=Column(
            Enum(RechargeOrderStatus, name="recharge_order_status"), nullable=False, index=True, comment="充值订单状态"
        ),
    )
    paid_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), comment="支付成功时间"))
    updated_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
            onupdate=func.now(),
            comment="最近状态变更时间",
        ),
    )
