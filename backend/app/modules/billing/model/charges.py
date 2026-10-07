"""计费报价、扣费状态枚举与扣费单 ORM 模型。

本模块只声明报价快照和扣费生命周期的持久化结构；价格计算、资金编排和事务提交分别由应用服务与调用方负责。
"""

import enum
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, Column, DateTime, Enum, ForeignKey, Index, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field

from app.core.database import SQLModelBase


class ChargeStatus(str, enum.Enum):
    """扣费单状态，记录预占到释放或结算的资金生命周期。"""

    reserved = "reserved"
    settled = "settled"
    released = "released"
    refunded = "refunded"


class ChargeType(str, enum.Enum):
    """扣费单对应的资金业务类型。"""

    video_generation = "video_generation"


class PriceQuote(SQLModelBase, table=True):
    """任务创建时冻结的不可变报价快照，避免后续改价影响历史任务。"""

    __tablename__ = "price_quotes"

    id: UUID = Field(default_factory=uuid4, primary_key=True, description="报价快照主键")
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now(), comment="报价冻结时间"),
    )
    user_id: UUID = Field(
        sa_column=Column(
            ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True, comment="请求报价的用户"
        )
    )
    provider: str = Field(sa_column=Column(String(32), nullable=False, comment="报价对应的提供方"))
    model: str = Field(sa_column=Column(String(64), nullable=False, comment="报价对应的平台模型"))
    workflow_id: str | None = Field(default=None, sa_column=Column(String(64), comment="报价对应的工作流"))
    currency: str = Field(sa_column=Column(String(3), nullable=False, comment="报价币种"))
    estimated_amount: Decimal = Field(
        sa_column=Column(Numeric(18, 6), nullable=False, comment="预估人民币 Decimal 金额")
    )
    calculation_snapshot: dict = Field(
        default_factory=dict, sa_column=Column(JSONB, nullable=False, comment="不可变计算明细")
    )


class Charge(SQLModelBase, table=True):
    """资金预占、结算和释放的业务状态记录，不替代不可变账本。"""

    __tablename__ = "charges"
    __table_args__ = (
        CheckConstraint("reserved_amount >= 0", name="ck_charges_reserved_nonnegative"),
        Index("ix_charges_video_task_id_status", "video_task_id", "status"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True, description="扣费单主键")
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now(), comment="扣费单创建时间"),
    )
    user_id: UUID = Field(
        sa_column=Column(
            ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True, comment="承担费用的用户"
        )
    )
    wallet_id: UUID = Field(
        sa_column=Column(
            ForeignKey("wallets.id", ondelete="RESTRICT"), nullable=False, index=True, comment="资金来源钱包"
        )
    )
    quote_id: UUID = Field(
        sa_column=Column(
            ForeignKey("price_quotes.id", ondelete="RESTRICT"), nullable=False, unique=True, comment="关联的不可变报价"
        )
    )
    video_task_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            ForeignKey("video_tasks.id", ondelete="RESTRICT"),
            unique=True,
            index=True,
            comment="关联视频任务，确保一个任务只对应一笔扣费单",
        ),
    )
    charge_type: ChargeType = Field(
        sa_column=Column(Enum(ChargeType, name="charge_type"), nullable=False, comment="收费业务类型")
    )
    status: ChargeStatus = Field(
        default=ChargeStatus.reserved,
        sa_column=Column(
            Enum(ChargeStatus, name="charge_status"), nullable=False, index=True, comment="独立资金生命周期状态"
        ),
    )
    reserved_amount: Decimal = Field(sa_column=Column(Numeric(18, 6), nullable=False, comment="已预占人民币金额"))
    settled_amount: Decimal | None = Field(default=None, sa_column=Column(Numeric(18, 6), comment="最终结算人民币金额"))
    context: dict = Field(
        default_factory=dict, sa_column=Column(JSONB, nullable=False, comment="业务审计上下文，不含密钥或支付凭据")
    )
