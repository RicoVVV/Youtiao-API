"""新增缓存写入计费项、使用记录缓存写入用量与定价规则默认币种。

本迁移是幂等的：约束按存在性重建，字段按存在性新增，默认值变更可重复执行，
以兼容由初始迁移动态建表的空库与已执行旧版本迁移的既有库。
"""

from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy import Column, Integer

revision = "0009_add_cache_write_pricing_item_kind"
down_revision = "0008_add_pricing_item_estimate_config"
branch_labels = None
depends_on = None

_KIND_VALUES = (
    "output_video_duration",
    "input_video_duration",
    "input_image_fixed",
    "input_material_tokens",
    "output_image_count",
    "input_image_tokens",
    "output_image_tokens",
    "input_text_tokens",
    "cache_write_input_text_tokens",
    "cached_input_text_tokens",
    "output_text_tokens",
    "request_fixed",
)
_LEGACY_KIND_VALUES = tuple(kind for kind in _KIND_VALUES if kind != "cache_write_input_text_tokens")
_KIND_CONSTRAINT = "ck_pricing_items_kind"
_CHECK_CONSTRAINT_TYPE = "check"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())
    _replace_kind_constraint(inspector, table_names=table_names, kind_values=_KIND_VALUES)
    _add_cache_write_column(inspector, table_names=table_names)
    _set_currency_default(table_names=table_names, default="USD")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())
    _replace_kind_constraint(inspector, table_names=table_names, kind_values=_LEGACY_KIND_VALUES)
    if "usage_records" in table_names:
        columns = {column["name"] for column in inspector.get_columns("usage_records")}
        if "cache_write_tokens" in columns:
            op.drop_column("usage_records", "cache_write_tokens")
    _set_currency_default(table_names=table_names, default="CNY")


def _replace_kind_constraint(inspector: Any, *, table_names: set[str], kind_values: tuple[str, ...]) -> None:
    """按存在性重建计费项类别约束，避免历史库缺少或形态不同导致迁移失败。"""

    if "pricing_items" not in table_names:
        return
    existing = {item["name"] for item in inspector.get_check_constraints("pricing_items")}
    if _KIND_CONSTRAINT in existing:
        op.drop_constraint(_KIND_CONSTRAINT, "pricing_items", type_=_CHECK_CONSTRAINT_TYPE)
    values = ", ".join(f"'{kind}'" for kind in kind_values)
    op.create_check_constraint(_KIND_CONSTRAINT, "pricing_items", f"kind IN ({values})")


def _add_cache_write_column(inspector: Any, *, table_names: set[str]) -> None:
    if "usage_records" not in table_names:
        return
    columns = {column["name"] for column in inspector.get_columns("usage_records")}
    if "cache_write_tokens" not in columns:
        op.add_column("usage_records", Column("cache_write_tokens", Integer, nullable=True))


def _set_currency_default(*, table_names: set[str], default: str) -> None:
    if "pricing_rules" not in table_names:
        return
    op.alter_column("pricing_rules", "currency", existing_type=sa.String(length=8), server_default=default)
