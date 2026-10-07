"""计费方案与定向修正项的 ORM 映射。

本模块只定义计费方案（``PricingRule``）与方案内修正项（``PricingModifier``）的表结构、
约束和索引；计费项本身见 ``app.modules.pricing.model.pricing_item``。报价计算由
``app.modules.pricing.application.engine`` 纯函数完成，不在此处承载业务编排。
"""

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

_SCOPE_TYPES = "'item_ids', 'item_kind', 'all_items'"


class PricingRule(SQLModelBase, table=True):
    """视频模型在指定令牌组下的计费方案。

    方案保留模型、令牌组、优先级和条件，用于在选择阶段命中最合适的一条；具体金额拆分为
    多个计费项，见 ``PricingItem``。同一模型与令牌组下启用方案的优先级必须唯一。
    """

    __tablename__ = "pricing_rules"
    __table_args__ = (
        Index(
            "uq_pricing_rules_model_group_priority_active",
            "model_id",
            "token_group_id",
            "priority",
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
    name: str = Field(sa_column=Column(String(128), nullable=False))
    priority: int = Field(sa_column=Column(Integer, nullable=False))
    conditions: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSONB, nullable=False))
    currency: str = Field(default="USD", sa_column=Column(String(8), nullable=False, server_default="USD"))
    active: bool = Field(default=True, sa_column=Column(Boolean, nullable=False, index=True))


class PricingModifier(SQLModelBase, table=True):
    """方案内的定向修正项，可覆盖单项原价或按优先级叠加倍率。

    ``fixed_price`` 只作用于单一计费项；``multiplier`` 可作用于多个计费项、一个计费项类别或全部
    计费项。作用范围由 ``scope_type`` 与对应集合字段共同决定。
    """

    __tablename__ = "pricing_modifiers"
    __table_args__ = (
        CheckConstraint("effect_type IN ('multiplier', 'fixed_price')", name="ck_pricing_modifiers_effect_type"),
        CheckConstraint(f"scope_type IN ({_SCOPE_TYPES})", name="ck_pricing_modifiers_scope_type"),
        Index(
            "uq_pricing_modifiers_rule_priority_active",
            "pricing_rule_id",
            "priority",
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
    pricing_rule_id: UUID = Field(
        sa_column=Column(ForeignKey("pricing_rules.id", ondelete="RESTRICT"), nullable=False, index=True)
    )
    name: str = Field(sa_column=Column(String(128), nullable=False))
    priority: int = Field(sa_column=Column(Integer, nullable=False))
    conditions: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSONB, nullable=False))
    effect_type: str = Field(sa_column=Column(String(32), nullable=False))
    effect_payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))
    scope_type: str = Field(
        default="all_items",
        sa_column=Column(String(16), nullable=False, server_default="all_items"),
    )
    scope_item_ids: list[str] = Field(default_factory=list, sa_column=Column(JSONB, nullable=False))
    scope_item_kinds: list[str] = Field(default_factory=list, sa_column=Column(JSONB, nullable=False))
    active: bool = Field(default=True, sa_column=Column(Boolean, nullable=False, index=True))
