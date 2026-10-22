"""新增用户余额预警开关与提醒状态表。

- 系统设置新增余额预警总开关列；
- 新建 balance_alert_states 表，记录每轮低余额提醒的发送状态；
- 全部使用存在性检查：由初始迁移按新元数据建表的空库，本迁移为空操作。

Revision ID: 0005_add_balance_alerts
Revises: 0004_pricing_currency_cny
Create Date: 2026-10-21
"""

import sqlalchemy as sa
from alembic import op
from app.bootstrap.model_registry import load_models
from app.core.database import SQLModelBase

revision = "0005_add_balance_alerts"
down_revision = "0004_pricing_currency_cny"
branch_labels = None
depends_on = None

_SETTINGS_TABLE = "system_settings"
_ALERT_STATE_TABLE = "balance_alert_states"
_SETTINGS_COLUMNS = (sa.Column("balance_alert_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),)


def upgrade() -> None:
    """补齐余额预警设置列与提醒状态表；已存在的对象不做任何变更。"""

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table(_SETTINGS_TABLE):
        existing_columns = {column["name"] for column in inspector.get_columns(_SETTINGS_TABLE)}
        for column in _SETTINGS_COLUMNS:
            if column.name not in existing_columns:
                op.add_column(_SETTINGS_TABLE, column)
    load_models()
    table = SQLModelBase.metadata.tables.get(_ALERT_STATE_TABLE)
    if table is not None:
        table.create(bind, checkfirst=True)


def downgrade() -> None:
    """删除提醒状态表与余额预警设置列。"""

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table(_ALERT_STATE_TABLE):
        op.drop_table(_ALERT_STATE_TABLE)
    if inspector.has_table(_SETTINGS_TABLE):
        existing_columns = {column["name"] for column in inspector.get_columns(_SETTINGS_TABLE)}
        for column in reversed(_SETTINGS_COLUMNS):
            if column.name in existing_columns:
                op.drop_column(_SETTINGS_TABLE, column.name)
