"""计费项的 ORM 映射。

计费项是计费方案的组成单元，描述某一类可计费用的计量来源、免费额度和基础单价。
本模块只定义表结构、约束和索引，不承载计量、报价或折扣计算逻辑。
"""

import enum
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field

from app.core.database import SQLModelBase


class PricingItemKind(str, enum.Enum):
    """计费项支持的计量类别，覆盖视频、图片与文本能力。"""

    output_video_duration = "output_video_duration"
    input_video_duration = "input_video_duration"
    input_image_fixed = "input_image_fixed"
    input_material_tokens = "input_material_tokens"
    output_image_count = "output_image_count"
    input_image_tokens = "input_image_tokens"
    output_image_tokens = "output_image_tokens"
    input_text_tokens = "input_text_tokens"
    cache_write_input_text_tokens = "cache_write_input_text_tokens"
    cached_input_text_tokens = "cached_input_text_tokens"
    output_text_tokens = "output_text_tokens"
    request_fixed = "request_fixed"


_KINDS = ", ".join(f"'{kind.value}'" for kind in PricingItemKind)


class PricingItem(SQLModelBase, table=True):
    """计费方案内的单个计费项。

    ``output_video_duration`` 的数量来自模型契约校验过的输出时长字段，必须自带 ``unit_amount``；
    ``input_video_duration`` 的数量来自实测输入视频时长，可通过 ``price_source_item_id`` 复用同方案
    输出项的基础单价；``input_image_fixed`` 按图片数量扣除 ``free_quantity`` 后乘以 ``unit_amount``；
    ``output_image_count`` 按请求字段（如图片张数）计量；
    ``input_text_tokens`` 按上游返回的未命中缓存输入 token 计量；``cache_write_input_text_tokens``
    按上游返回的缓存写入输入 token 计量；``cached_input_text_tokens`` 按命中缓存的输入 token 计量；
    ``output_text_tokens`` 按输出 token 计量，四类文本 Token 项的 ``unit_amount`` 均为每百万 Token
    单价；``request_fixed`` 按次固定计费。
    """

    __tablename__ = "pricing_items"
    __table_args__ = (
        CheckConstraint(f"kind IN ({_KINDS})", name="ck_pricing_items_kind"),
        CheckConstraint("unit_amount IS NULL OR unit_amount >= 0", name="ck_pricing_items_unit_amount_non_negative"),
        CheckConstraint("free_quantity >= 0", name="ck_pricing_items_free_quantity_non_negative"),
        Index(
            "uq_pricing_items_rule_position_active",
            "pricing_rule_id",
            "position",
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
    label: str = Field(sa_column=Column(String(128), nullable=False))
    position: int = Field(sa_column=Column(Integer, nullable=False))
    kind: str = Field(sa_column=Column(String(32), nullable=False))
    source_fields: list[str] = Field(default_factory=list, sa_column=Column(JSONB, nullable=False))
    estimate_config: dict[str, object] = Field(
        default_factory=dict, sa_column=Column(JSONB, nullable=False, server_default="{}")
    )
    free_quantity: int = Field(default=0, sa_column=Column(Integer, nullable=False, server_default="0"))
    unit_amount: Decimal | None = Field(default=None, sa_column=Column(Numeric(18, 6), nullable=True))
    price_source_item_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            ForeignKey("pricing_items.id", ondelete="RESTRICT"),
            nullable=True,
            index=True,
            comment="输入视频项目引用的同方案输出时长项目，用于复用其基础单价",
        ),
    )
    active: bool = Field(default=True, sa_column=Column(Boolean, nullable=False, index=True))
