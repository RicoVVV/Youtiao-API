"""把余额预警阈值从系统设置迁移到用户账号。

- users 新增用户自设的余额预警阈值列；
- 清理早期版本在 system_settings 上创建的全局阈值列；
- 全部使用存在性检查，兼容新旧库。

Revision ID: 0006_move_balance_alert_threshold_to_users
Revises: 0005_add_balance_alerts
Create Date: 2026-10-21
"""

import sqlalchemy as sa
from alembic import op

revision = "0006_move_balance_alert_threshold_to_users"
down_revision = "0005_add_balance_alerts"
branch_labels = None
depends_on = None

_USERS_TABLE = "users"
_SETTINGS_TABLE = "system_settings"
_USER_THRESHOLD_COLUMN = "balance_alert_threshold"


def upgrade() -> None:
    """新增用户阈值列，并移除系统设置上的旧全局阈值列。"""

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table(_USERS_TABLE):
        columns = {column["name"] for column in inspector.get_columns(_USERS_TABLE)}
        if _USER_THRESHOLD_COLUMN not in columns:
            op.add_column(
                _USERS_TABLE,
                sa.Column(
                    _USER_THRESHOLD_COLUMN,
                    sa.Numeric(18, 6),
                    nullable=True,
                    comment="用户自设余额预警阈值（CNY），为空表示不接收余额预警邮件",
                ),
            )
    if inspector.has_table(_SETTINGS_TABLE):
        columns = {column["name"] for column in inspector.get_columns(_SETTINGS_TABLE)}
        if _USER_THRESHOLD_COLUMN in columns:
            op.drop_column(_SETTINGS_TABLE, _USER_THRESHOLD_COLUMN)


def downgrade() -> None:
    """恢复系统设置上的全局阈值列，并移除用户阈值列。"""

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table(_SETTINGS_TABLE):
        columns = {column["name"] for column in inspector.get_columns(_SETTINGS_TABLE)}
        if _USER_THRESHOLD_COLUMN not in columns:
            op.add_column(
                _SETTINGS_TABLE,
                sa.Column(_USER_THRESHOLD_COLUMN, sa.Numeric(18, 6), nullable=False, server_default=sa.text("1")),
            )
    if inspector.has_table(_USERS_TABLE):
        columns = {column["name"] for column in inspector.get_columns(_USERS_TABLE)}
        if _USER_THRESHOLD_COLUMN in columns:
            op.drop_column(_USERS_TABLE, _USER_THRESHOLD_COLUMN)
