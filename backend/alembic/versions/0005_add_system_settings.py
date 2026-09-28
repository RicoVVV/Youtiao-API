import sqlalchemy as sa
from alembic import op
from sqlalchemy import Boolean, Column, DateTime, String, Text, Uuid, func

revision = "0005_add_system_settings"
down_revision = "0004_add_channel_latest_test_snapshot"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "system_settings" not in inspector.get_table_names():
        op.create_table(
            "system_settings",
            Column("id", Uuid(), nullable=False),
            Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
            Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
            Column("system_name", String(length=255), nullable=False, server_default=""),
            Column("server_url", String(length=2048), nullable=False, server_default=""),
            Column("logo_url", String(length=2048), nullable=False, server_default=""),
            Column("footer_text", String(length=2000), nullable=False, server_default=""),
            Column("about_content", Text(), nullable=False, server_default=""),
            Column("homepage_content", Text(), nullable=False, server_default=""),
            Column("terms_of_service", Text(), nullable=False, server_default=""),
            Column("privacy_policy", Text(), nullable=False, server_default=""),
            Column("is_del", Boolean(), nullable=False, server_default="false"),
            sa.PrimaryKeyConstraint("id"),
        )
        return
    columns = {column["name"] for column in inspector.get_columns("system_settings")}
    if "created_at" not in columns:
        op.add_column(
            "system_settings",
            Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
        )
    if "updated_at" not in columns:
        op.add_column(
            "system_settings",
            Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
        )


def downgrade() -> None:
    if "system_settings" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table("system_settings")
