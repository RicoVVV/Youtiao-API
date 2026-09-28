"""新增 Token 分组介绍字段。

Revision ID: 0011_add_token_group_description
Revises: 0010_add_token_group_price_multiplier
Create Date: 2026-09-18
"""

import sqlalchemy as sa
from alembic import op

revision = "0011_add_token_group_description"
down_revision = "0010_add_token_group_price_multiplier"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "token_groups" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("token_groups")}
    if "description" not in columns:
        op.add_column(
            "token_groups",
            sa.Column("description", sa.String(512), nullable=False, server_default=""),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "token_groups" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("token_groups")}
    if "description" in columns:
        op.drop_column("token_groups", "description")
