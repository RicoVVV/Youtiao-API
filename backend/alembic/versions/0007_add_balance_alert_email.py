"""为用户新增余额预警收件邮箱列。

- users 增加 balance_alert_email，用户未设置时回退使用注册邮箱；
- 使用存在性检查，由初始迁移按新元数据建表的空库为空操作。

Revision ID: 0007_add_balance_alert_email
Revises: 0006_move_balance_alert_threshold_to_users
Create Date: 2026-10-21
"""

import sqlalchemy as sa
from alembic import op

revision = "0007_add_balance_alert_email"
down_revision = "0006_move_balance_alert_threshold_to_users"
branch_labels = None
depends_on = None

_USERS_TABLE = "users"
_COLUMN = "balance_alert_email"


def upgrade() -> None:
    """为用户表补充余额预警收件邮箱列。"""

    inspector = sa.inspect(op.get_bind())
    if _USERS_TABLE not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns(_USERS_TABLE)}
    if _COLUMN not in columns:
        op.add_column(
            _USERS_TABLE,
            sa.Column(
                _COLUMN,
                sa.String(320),
                nullable=True,
                comment="用户自设的余额预警收件邮箱，为空时使用注册邮箱",
            ),
        )


def downgrade() -> None:
    """移除余额预警收件邮箱列。"""

    inspector = sa.inspect(op.get_bind())
    if _USERS_TABLE not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns(_USERS_TABLE)}
    if _COLUMN in columns:
        op.drop_column(_USERS_TABLE, _COLUMN)
