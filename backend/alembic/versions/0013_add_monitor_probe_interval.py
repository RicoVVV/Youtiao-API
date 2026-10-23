"""为分组监控模式配置增加可调嗅探周期。

- monitor_traffic_settings 增加 probe_interval_seconds，默认 60 秒；
- 使用存在性检查，由初始迁移按新元数据建表的空库为空操作。

Revision ID: 0013_add_monitor_probe_interval
Revises: 0012_add_group_monitor_probe
Create Date: 2026-10-23
"""

import sqlalchemy as sa
from alembic import op

revision = "0013_add_monitor_probe_interval"
down_revision = "0012_add_group_monitor_probe"
branch_labels = None
depends_on = None

_TABLE = "monitor_traffic_settings"
_COLUMN = "probe_interval_seconds"


def upgrade() -> None:
    """补充嗅探周期配置列。"""

    inspector = sa.inspect(op.get_bind())
    if _TABLE not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns(_TABLE)}
    if _COLUMN not in columns:
        op.add_column(
            _TABLE,
            sa.Column(
                _COLUMN,
                sa.Integer(),
                nullable=False,
                server_default="60",
                comment="嗅探模式下两次分组文本探测之间的间隔秒数",
            ),
        )


def downgrade() -> None:
    """移除嗅探周期配置列。"""

    inspector = sa.inspect(op.get_bind())
    if _TABLE not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns(_TABLE)}
    if _COLUMN in columns:
        op.drop_column(_TABLE, _COLUMN)
