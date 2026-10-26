"""邀请返利 ORM 模型，保存用户邀请码、上级关系、返利额度与不可变流水。"""

import enum
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    func,
    text,
)
from sqlmodel import Field

from app.core.database import SQLModelBase


class AffiliateLedgerAction(str, enum.Enum):
    """返利流水业务动作。"""

    accrue = "accrue"
    transfer = "transfer"


class UserAffiliate(SQLModelBase, table=True):
    """用户邀请返利档案：一用户一行，保存邀请码、上级与三池额度。"""

    __tablename__ = "user_affiliates"
    __table_args__ = (Index("ix_user_affiliates_inviter_id", "inviter_id"),)

    user_id: UUID = Field(
        sa_column=Column(
            ForeignKey("users.id", ondelete="RESTRICT"),
            primary_key=True,
            comment="返利档案所属用户",
        )
    )
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now(), comment="档案创建时间"),
    )
    aff_code: str = Field(
        sa_column=Column(String(32), unique=True, nullable=False, comment="用户邀请码，系统生成或管理员改写")
    )
    inviter_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
            comment="邀请人用户标识；绑定后不可更改",
        ),
    )
    aff_count: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False, server_default="0", comment="累计绑定的被邀请人数量"),
    )
    available_quota: Decimal = Field(
        default=Decimal("0"),
        sa_column=Column(Numeric(18, 6), nullable=False, server_default="0", comment="当前可转入余额的返利额度"),
    )
    frozen_quota: Decimal = Field(
        default=Decimal("0"),
        sa_column=Column(Numeric(18, 6), nullable=False, server_default="0", comment="冻结期内的返利额度"),
    )
    history_quota: Decimal = Field(
        default=Decimal("0"),
        sa_column=Column(Numeric(18, 6), nullable=False, server_default="0", comment="累计产生的返利总额"),
    )
    rebate_rate_percent: Decimal | None = Field(
        default=None,
        sa_column=Column(
            Numeric(5, 2),
            nullable=True,
            comment="用户作为邀请人时的专属返利比例（百分比）；为空时沿用全局比例",
        ),
    )
    aff_code_custom: bool = Field(
        default=False,
        sa_column=Column(
            Boolean,
            nullable=False,
            server_default="false",
            comment="邀请码是否由管理员手动改写",
        ),
    )
    updated_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
            onupdate=func.now(),
            comment="最近一次额度或关系变更时间",
        ),
    )


class AffiliateLedger(SQLModelBase, table=True):
    """邀请返利资金流水：返利产生与转入余额各追加一条不可变记录。"""

    __tablename__ = "affiliate_ledgers"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_affiliate_ledgers_amount_positive"),
        Index(
            "uq_affiliate_ledger_accrue_order",
            "source_order_id",
            unique=True,
            postgresql_where=text("action = 'accrue' AND source_order_id IS NOT NULL"),
        ),
        Index("ix_affiliate_ledgers_user_created_at", "user_id", "created_at"),
        Index(
            "ix_affiliate_ledgers_frozen",
            "user_id",
            "frozen_until",
            postgresql_where=text("frozen_until IS NOT NULL"),
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True, description="返利流水主键")
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now(), comment="流水创建时间"),
    )
    user_id: UUID = Field(
        sa_column=Column(
            ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
            comment="返利归属用户或转出用户",
        )
    )
    action: AffiliateLedgerAction = Field(
        sa_column=Column(
            Enum(AffiliateLedgerAction, name="affiliate_ledger_action"),
            nullable=False,
            comment="流水动作：accrue 返利产生，transfer 转入余额",
        )
    )
    amount: Decimal = Field(sa_column=Column(Numeric(18, 6), nullable=False, comment="本次返利或转出金额（USD）"))
    source_user_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
            comment="产生返利的被邀请人；账号删除后置空",
        ),
    )
    source_order_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            ForeignKey("recharge_orders.id", ondelete="SET NULL"),
            nullable=True,
            comment="产生返利的充值或会员订单；转入余额流水为空",
        ),
    )
    frozen_until: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True),
            nullable=True,
            comment="返利冻结到期时间；为空表示已解冻或从未冻结",
        ),
    )
    balance_after: Decimal | None = Field(
        default=None,
        sa_column=Column(Numeric(18, 6), nullable=True, comment="转入余额后的钱包余额快照"),
    )
    available_quota_after: Decimal | None = Field(
        default=None,
        sa_column=Column(Numeric(18, 6), nullable=True, comment="转入余额后的可用返利额度快照"),
    )
    frozen_quota_after: Decimal | None = Field(
        default=None,
        sa_column=Column(Numeric(18, 6), nullable=True, comment="转入余额后的冻结返利额度快照"),
    )
    history_quota_after: Decimal | None = Field(
        default=None,
        sa_column=Column(Numeric(18, 6), nullable=True, comment="转入余额后的累计返利额度快照"),
    )
    updated_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
            onupdate=func.now(),
            comment="流水最近一次状态变更时间",
        ),
    )


__all__ = [
    "AffiliateLedger",
    "AffiliateLedgerAction",
    "UserAffiliate",
]
