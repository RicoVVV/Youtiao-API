import sqlalchemy as sa
from alembic import op
from sqlalchemy import Column, Integer

revision = "0007_add_usage_record_first_token_duration"
down_revision = "0006_add_video_result_download_failed_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "usage_records" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("usage_records")}
    if "first_token_duration_ms" not in columns:
        op.add_column("usage_records", Column("first_token_duration_ms", Integer, nullable=True))


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "usage_records" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("usage_records")}
    if "first_token_duration_ms" in columns:
        op.drop_column("usage_records", "first_token_duration_ms")
