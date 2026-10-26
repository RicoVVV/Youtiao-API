"""调整邀请返利默认值：默认关闭、返利 5%、冻结 5 小时。

Revision ID: 0018_affiliate_default_values
Revises: 0017_add_affiliate
Create Date: 2026-10-26
"""

import sqlalchemy as sa
from alembic import op

revision = "0018_affiliate_default_values"
down_revision = "0017_add_affiliate"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """更新列默认值；邀请返利保持默认关闭，由管理员在后台显式开启。"""

    op.alter_column(
        "system_settings",
        "affiliate_enabled",
        existing_type=sa.Boolean(),
        existing_nullable=False,
        server_default="false",
    )
    op.alter_column(
        "system_settings",
        "affiliate_rebate_rate_percent",
        existing_type=sa.Numeric(5, 2),
        existing_nullable=False,
        server_default="5.00",
    )
    op.alter_column(
        "system_settings",
        "affiliate_rebate_freeze_hours",
        existing_type=sa.Integer(),
        existing_nullable=False,
        server_default="5",
    )


def downgrade() -> None:
    """恢复旧列默认值；已迁移的数据保持不变，避免覆盖管理员配置。"""

    op.alter_column(
        "system_settings",
        "affiliate_enabled",
        existing_type=sa.Boolean(),
        existing_nullable=False,
        server_default="false",
    )
    op.alter_column(
        "system_settings",
        "affiliate_rebate_rate_percent",
        existing_type=sa.Numeric(5, 2),
        existing_nullable=False,
        server_default="20.00",
    )
    op.alter_column(
        "system_settings",
        "affiliate_rebate_freeze_hours",
        existing_type=sa.Integer(),
        existing_nullable=False,
        server_default="0",
    )
