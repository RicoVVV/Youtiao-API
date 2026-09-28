from alembic import op
from sqlalchemy import Column, inspect
from sqlalchemy.dialects.postgresql import JSONB

revision = "0004_add_channel_latest_test_snapshot"
down_revision = "0003_channel_model_mapping_names"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "channels" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("channels")}
    if "latest_test_snapshot" not in columns:
        op.add_column("channels", Column("latest_test_snapshot", JSONB, nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "channels" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("channels")}
    if "latest_test_snapshot" in columns:
        op.drop_column("channels", "latest_test_snapshot")
