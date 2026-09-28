import sqlalchemy as sa
from alembic import op
from sqlalchemy import Column, DateTime

revision = "0006_add_video_result_download_failed_at"
down_revision = "0005_add_system_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "video_tasks" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("video_tasks")}
    if "result_download_failed_at" not in columns:
        op.add_column("video_tasks", Column("result_download_failed_at", DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "video_tasks" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("video_tasks")}
    if "result_download_failed_at" in columns:
        op.drop_column("video_tasks", "result_download_failed_at")
