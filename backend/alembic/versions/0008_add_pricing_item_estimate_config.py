import sqlalchemy as sa
from alembic import op
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB

revision = "0008_add_pricing_item_estimate_config"
down_revision = "0007_add_usage_record_first_token_duration"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "pricing_items" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("pricing_items")}
    if "estimate_config" not in columns:
        op.add_column(
            "pricing_items",
            Column(
                "estimate_config",
                JSONB if bind.dialect.name == "postgresql" else sa.JSON(),
                nullable=False,
                server_default="{}",
            ),
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "pricing_items" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("pricing_items")}
    if "estimate_config" in columns:
        op.drop_column("pricing_items", "estimate_config")
