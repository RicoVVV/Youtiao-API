"""新增邀请返利：用户档案、返利流水、系统设置与余额流水类型。

Revision ID: 0017_add_affiliate
Revises: 0016_add_usage_record_created_at_index
Create Date: 2026-10-26
"""

import sqlalchemy as sa
from alembic import op
from app.bootstrap.model_registry import load_models
from app.core.database import SQLModelBase
from sqlalchemy.dialects import postgresql

revision = "0017_add_affiliate"
down_revision = "0016_add_usage_record_created_at_index"
branch_labels = None
depends_on = None

_NEW_TABLES = ("user_affiliates", "affiliate_ledgers")
_SYSTEM_SETTING_COLUMNS = (
    sa.Column("affiliate_enabled", sa.Boolean(), nullable=False, server_default="false"),
    sa.Column("affiliate_rebate_rate_percent", sa.Numeric(5, 2), nullable=False, server_default="20.00"),
    sa.Column("affiliate_rebate_freeze_hours", sa.Integer(), nullable=False, server_default="0"),
    sa.Column("affiliate_rebate_duration_days", sa.Integer(), nullable=False, server_default="0"),
    sa.Column("affiliate_rebate_per_invitee_cap", sa.Numeric(18, 6), nullable=False, server_default="0"),
)


def _add_column_if_missing(inspector: sa.Inspector, table: str, column: sa.Column) -> None:
    """仅在列缺失时新增，兼容由初始迁移按新元数据建表的空库。"""

    if column.name not in {item["name"] for item in inspector.get_columns(table)}:
        op.add_column(table, column)


def upgrade() -> None:
    """创建邀请返利表、设置列并扩展余额流水枚举。"""

    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE balance_record_type ADD VALUE IF NOT EXISTS 'affiliate_rebate'")

    bind = op.get_bind()
    load_models()
    for table_name in _NEW_TABLES:
        SQLModelBase.metadata.tables[table_name].create(bind, checkfirst=True)

    inspector = sa.inspect(bind)
    if "system_settings" in inspector.get_table_names():
        for column in _SYSTEM_SETTING_COLUMNS:
            _add_column_if_missing(inspector, "system_settings", column)


def downgrade() -> None:
    """移除邀请返利表与设置列；PostgreSQL 不支持删除枚举值，保留 affiliate_rebate。"""

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "system_settings" in inspector.get_table_names():
        existing = {item["name"] for item in inspector.get_columns("system_settings")}
        for column in reversed(_SYSTEM_SETTING_COLUMNS):
            if column.name in existing:
                op.drop_column("system_settings", column.name)

    for table_name in reversed(_NEW_TABLES):
        if inspector.has_table(table_name):
            op.drop_table(table_name)
    postgresql.ENUM(name="affiliate_ledger_action").drop(bind, checkfirst=True)
