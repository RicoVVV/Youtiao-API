"""新增邀请注册赠送额度配置与余额流水类型。

Revision ID: 0020_add_affiliate_signup_bonus
Revises: 0019_backfill_deleted_usernames
Create Date: 2026-10-26
"""

import sqlalchemy as sa
from alembic import op

revision = "0020_add_affiliate_signup_bonus"
down_revision = "0019_backfill_deleted_usernames"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """扩展余额流水枚举，并新增邀请注册赠送额度设置列。"""

    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE balance_record_type ADD VALUE IF NOT EXISTS 'signup_bonus'")

    inspector = sa.inspect(op.get_bind())
    if "system_settings" in inspector.get_table_names():
        existing = {item["name"] for item in inspector.get_columns("system_settings")}
        if "affiliate_signup_bonus" not in existing:
            op.add_column(
                "system_settings",
                sa.Column(
                    "affiliate_signup_bonus",
                    sa.Numeric(18, 6),
                    nullable=False,
                    server_default="0",
                    comment="通过邀请码或邀请链接注册的新用户赠送余额（USD），0 表示不赠送",
                ),
            )


def downgrade() -> None:
    """移除赠送额度设置列；PostgreSQL 不支持删除枚举值，保留 signup_bonus。"""

    inspector = sa.inspect(op.get_bind())
    if "system_settings" in inspector.get_table_names():
        existing = {item["name"] for item in inspector.get_columns("system_settings")}
        if "affiliate_signup_bonus" in existing:
            op.drop_column("system_settings", "affiliate_signup_bonus")
