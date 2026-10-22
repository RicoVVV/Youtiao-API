"""为渠道增加健康探测自动停用时间列。

- channels 增加 auto_disabled_at，用于区分自动停用与人工停用；
- 使用存在性检查，由初始迁移按新元数据建表的空库为空操作。

Revision ID: 0008_add_channel_auto_disabled_at
Revises: 0007_add_balance_alert_email
Create Date: 2026-10-22
"""

import sqlalchemy as sa
from alembic import op

revision = "0008_add_channel_auto_disabled_at"
down_revision = "0007_add_balance_alert_email"
branch_labels = None
depends_on = None

_CHANNELS_TABLE = "channels"
_COLUMN = "auto_disabled_at"


def upgrade() -> None:
    """为渠道表补充自动停用时间列。"""

    inspector = sa.inspect(op.get_bind())
    if _CHANNELS_TABLE not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns(_CHANNELS_TABLE)}
    if _COLUMN not in columns:
        op.add_column(
            _CHANNELS_TABLE,
            sa.Column(
                _COLUMN,
                sa.DateTime(timezone=True),
                nullable=True,
                comment="健康探测自动停用时间，为空表示非自动停用",
            ),
        )


def downgrade() -> None:
    """移除渠道表自动停用时间列。"""

    inspector = sa.inspect(op.get_bind())
    if _CHANNELS_TABLE not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns(_CHANNELS_TABLE)}
    if _COLUMN in columns:
        op.drop_column(_CHANNELS_TABLE, _COLUMN)
