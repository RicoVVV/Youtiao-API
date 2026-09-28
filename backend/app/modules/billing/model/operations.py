"""计费运营场景 ORM 模型，保存管理员授予与兑换码事实。"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Numeric, String, func
from sqlmodel import Field

from app.core.database import SQLModelBase


class BillingAdjustment(SQLModelBase, table=True):
    """管理员余额授予记录，关联实际产生的余额明细。"""

    __tablename__ = "billing_adjustments"
    id: UUID = Field(default_factory=uuid4, primary_key=True, description="管理员调整记录主键")
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True), nullable=False, server_default=func.now(), comment="调整记录创建时间"
        ),
    )
    user_id: UUID = Field(
        sa_column=Column(ForeignKey("users.id"), nullable=False, index=True, comment="被调整余额的用户")
    )
    admin_id: UUID = Field(
        sa_column=Column(ForeignKey("users.id"), nullable=False, index=True, comment="执行调整的统一用户管理员")
    )
    amount: Decimal = Field(sa_column=Column(Numeric(18, 6), nullable=False, comment="非零有符号人民币金额"))
    reason: str = Field(sa_column=Column(String(256), nullable=False, comment="调整原因"))
    balance_record_id: UUID = Field(
        sa_column=Column(ForeignKey("balance_records.id"), nullable=False, unique=True, comment="对应余额变动明细")
    )


class RedemptionCode(SQLModelBase, table=True):
    """单码单次兑换码，保存明文兑换码、运营元数据与核销审计事实。"""

    __tablename__ = "redemption_codes"
    __table_args__ = (
        Index("ix_redemption_codes_active_created_at", "active", "created_at"),
        Index("ix_redemption_codes_expires_at", "expires_at"),
    )
    id: UUID = Field(default_factory=uuid4, primary_key=True, description="兑换码记录主键")
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now(), comment="兑换码创建时间"),
    )
    name: str = Field(sa_column=Column(String(128), nullable=False, comment="后台运营展示名称，允许重复"))
    remark: str | None = Field(default=None, sa_column=Column(String(512), comment="后台运营备注，不向核销用户展示"))
    expires_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), comment="兑换码失效时间；为空表示永久有效"),
    )
    created_by_admin_id: UUID | None = Field(
        default=None,
        sa_column=Column(ForeignKey("users.id"), index=True, comment="创建兑换码的管理员；历史记录为空表示未知"),
    )
    code: str = Field(
        sa_column=Column(String(128), nullable=False, unique=True, comment="完整明文兑换码，唯一且管理端可查看")
    )
    amount: Decimal = Field(sa_column=Column(Numeric(18, 6), nullable=False, comment="固定入账人民币金额"))
    active: bool = Field(default=True, sa_column=Column(Boolean, nullable=False, comment="停用后不可兑换"))
    redeemed_by_user_id: UUID | None = Field(
        default=None, sa_column=Column(ForeignKey("users.id"), comment="成功兑换用户；同一用户可兑换多张不同兑换码")
    )
    redeemed_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), comment="成功兑换时间")
    )
