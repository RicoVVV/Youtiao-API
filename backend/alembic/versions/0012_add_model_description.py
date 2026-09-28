"""新增模型介绍字段。

Revision ID: 0012_add_model_description
Revises: 0011_add_token_group_description
Create Date: 2026-09-18
"""

import sqlalchemy as sa
from alembic import op

revision = "0012_add_model_description"
down_revision = "0011_add_token_group_description"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "models" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("models")}
    if "description" not in columns:
        op.add_column("models", sa.Column("description", sa.String(512), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "models" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("models")}
    if "description" in columns:
        op.drop_column("models", "description")
