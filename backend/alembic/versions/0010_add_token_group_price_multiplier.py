"""新增 Token 分组价格倍率。

Revision ID: 0010_add_token_group_price_multiplier
Revises: 0009_add_cache_write_pricing_item_kind
Create Date: 2026-09-17
"""

import sqlalchemy as sa
from alembic import op

revision = "0010_add_token_group_price_multiplier"
down_revision = "0009_add_cache_write_pricing_item_kind"
branch_labels = None
depends_on = None

_CONSTRAINT = "ck_token_groups_price_multiplier_positive"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "token_groups" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("token_groups")}
    if "price_multiplier" not in columns:
        op.add_column(
            "token_groups",
            sa.Column("price_multiplier", sa.Numeric(18, 6), nullable=False, server_default="1.000000"),
        )
    constraints = {item["name"] for item in inspector.get_check_constraints("token_groups")}
    if _CONSTRAINT not in constraints:
        op.create_check_constraint(_CONSTRAINT, "token_groups", "price_multiplier > 0")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "token_groups" not in inspector.get_table_names():
        return
    constraints = {item["name"] for item in inspector.get_check_constraints("token_groups")}
    if _CONSTRAINT in constraints:
        op.drop_constraint(_CONSTRAINT, "token_groups", type_="check")
    columns = {column["name"] for column in inspector.get_columns("token_groups")}
    if "price_multiplier" in columns:
        op.drop_column("token_groups", "price_multiplier")
