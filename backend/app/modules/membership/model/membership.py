"""会员等级、套餐、等级专享分组、用户会员状态与会员变动流水的 ORM 映射。"""

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


class MembershipPeriod(str, enum.Enum):
    week = "week"
    month = "month"


class MembershipRecordSource(str, enum.Enum):
    purchase = "purchase"
    purchase_converted = "purchase_converted"
    admin_grant = "admin_grant"
    admin_revoke = "admin_revoke"


PERIOD_DAYS: dict[MembershipPeriod, int] = {MembershipPeriod.week: 7, MembershipPeriod.month: 30}


def _created_at_column(comment: str) -> Column:
    return Column(DateTime(timezone=True), nullable=False, server_default=func.now(), comment=comment)


def _updated_at_column(comment: str) -> Column:
    return Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(), comment=comment
    )


class MembershipLevel(SQLModelBase, table=True):
    """会员等级，rank 决定升降级。"""

    __tablename__ = "membership_levels"
    __table_args__ = (
        CheckConstraint("rank >= 1", name="ck_membership_levels_rank"),
        Index("uq_membership_levels_code_active", "code", unique=True, postgresql_where=text("is_del = false")),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True, description="会员等级主键")
    created_at: datetime | None = Field(default=None, sa_column=_created_at_column("等级创建时间"))
    updated_at: datetime | None = Field(default=None, sa_column=_updated_at_column("等级最近更新时间"))
    code: str = Field(sa_column=Column(String(32), nullable=False, comment="等级编码，未删除范围内唯一"))
    name: str = Field(sa_column=Column(String(64), nullable=False, comment="等级展示名称"))
    description: str = Field(
        default="", sa_column=Column(String(512), nullable=False, server_default="", comment="等级展示介绍")
    )
    rank: int = Field(sa_column=Column(Integer, nullable=False, comment="等级高低，数值越大等级越高"))
    is_public: bool = Field(
        default=True,
        sa_column=Column(Boolean, nullable=False, server_default="true", comment="是否对外售卖，false 仅管理员授予"),
    )
    is_active: bool = Field(
        default=True,
        sa_column=Column(Boolean, nullable=False, server_default="true", comment="停用后不可下单或授予"),
    )


class MembershipPlan(SQLModelBase, table=True):
    """会员等级在某一时长单位下的售卖套餐。"""

    __tablename__ = "membership_plans"
    __table_args__ = (
        CheckConstraint("price >= 0", name="ck_membership_plans_price"),
        CheckConstraint("bonus_amount >= 0", name="ck_membership_plans_bonus_amount"),
        Index(
            "uq_membership_plans_level_period_active",
            "level_id",
            "period",
            unique=True,
            postgresql_where=text("is_del = false"),
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True, description="会员套餐主键")
    created_at: datetime | None = Field(default=None, sa_column=_created_at_column("套餐创建时间"))
    updated_at: datetime | None = Field(default=None, sa_column=_updated_at_column("套餐最近更新时间"))
    level_id: UUID = Field(
        sa_column=Column(
            ForeignKey("membership_levels.id", ondelete="RESTRICT"), nullable=False, index=True, comment="所属等级"
        )
    )
    period: MembershipPeriod = Field(
        sa_column=Column(Enum(MembershipPeriod, name="membership_period"), nullable=False, comment="时长单位")
    )
    price: Decimal = Field(sa_column=Column(Numeric(18, 6), nullable=False, comment="人民币售价"))
    bonus_amount: Decimal = Field(
        default=Decimal("0"),
        sa_column=Column(Numeric(18, 6), nullable=False, server_default="0", comment="开通赠送余额"),
    )
    is_active: bool = Field(
        default=True,
        sa_column=Column(Boolean, nullable=False, server_default="true", comment="停用后不可下单或授予"),
    )


class MembershipLevelGroup(SQLModelBase, table=True):
    """会员等级关联的 restricted Token 专享分组。"""

    __tablename__ = "membership_level_groups"
    __table_args__ = (
        Index(
            "uq_membership_level_groups_level_group_active",
            "level_id",
            "group_id",
            unique=True,
            postgresql_where=text("is_del = false"),
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True, description="等级专享分组关系主键")
    created_at: datetime | None = Field(default=None, sa_column=_created_at_column("关联创建时间"))
    level_id: UUID = Field(
        sa_column=Column(
            ForeignKey("membership_levels.id", ondelete="RESTRICT"), nullable=False, index=True, comment="会员等级"
        )
    )
    group_id: int = Field(
        sa_column=Column(
            ForeignKey("token_groups.id", ondelete="RESTRICT"), nullable=False, index=True, comment="专享分组"
        )
    )


class UserMembership(SQLModelBase, table=True):
    """用户当前（或最近一次）会员状态，expires_at 大于当前时间即有效。"""

    __tablename__ = "user_memberships"
    __table_args__ = (Index("ix_user_memberships_expires_at", "expires_at"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True, description="用户会员主键")
    created_at: datetime | None = Field(default=None, sa_column=_created_at_column("首次开通时间"))
    updated_at: datetime | None = Field(default=None, sa_column=_updated_at_column("最近变更时间"))
    user_id: UUID = Field(
        sa_column=Column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, unique=True, comment="会员用户")
    )
    level_id: UUID = Field(
        sa_column=Column(
            ForeignKey("membership_levels.id", ondelete="RESTRICT"), nullable=False, index=True, comment="当前等级"
        )
    )
    started_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False, comment="本期起始时间"))
    expires_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False, comment="到期时间"))


class MembershipRecord(SQLModelBase, table=True):
    """会员变动的不可变审计流水。"""

    __tablename__ = "membership_records"
    __table_args__ = (
        CheckConstraint("quantity >= 1 AND quantity <= 12", name="ck_membership_records_quantity"),
        CheckConstraint("bonus_amount >= 0", name="ck_membership_records_bonus_amount"),
        Index("ix_membership_records_user_created_at", "user_id", "created_at"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True, description="会员流水主键")
    created_at: datetime | None = Field(default=None, sa_column=_created_at_column("流水创建时间"))
    user_id: UUID = Field(
        sa_column=Column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True, comment="会员用户")
    )
    source: MembershipRecordSource = Field(
        sa_column=Column(
            Enum(MembershipRecordSource, name="membership_record_source"), nullable=False, comment="变动来源"
        )
    )
    level_id: UUID = Field(
        sa_column=Column(ForeignKey("membership_levels.id", ondelete="RESTRICT"), nullable=False, comment="目标等级")
    )
    plan_id: UUID | None = Field(
        default=None,
        sa_column=Column(ForeignKey("membership_plans.id", ondelete="RESTRICT"), comment="套餐，撤销时为空"),
    )
    quantity: int = Field(default=1, sa_column=Column(Integer, nullable=False, server_default="1", comment="时长份数"))
    expires_before: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), comment="变动前到期时间")
    )
    expires_after: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), comment="变动后到期时间")
    )
    bonus_amount: Decimal = Field(
        default=Decimal("0"),
        sa_column=Column(Numeric(18, 6), nullable=False, server_default="0", comment="本次实际赠送余额"),
    )
    recharge_order_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            ForeignKey("recharge_orders.id", ondelete="RESTRICT"), unique=True, comment="购买来源订单，保证结算幂等"
        ),
    )
    operator_id: UUID | None = Field(
        default=None, sa_column=Column(ForeignKey("users.id", ondelete="RESTRICT"), comment="管理员操作人")
    )
    reason: str = Field(
        default="", sa_column=Column(String(256), nullable=False, server_default="", comment="变动原因")
    )
