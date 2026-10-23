"""将分组监控数据模式的默认值改为嗅探模式。

- monitor_traffic_settings.mode 的数据库默认值由 real 改为 probe；
- 不覆盖已有配置行，管理员显式选择过的 real 保持不变；
- 使用存在性检查，由初始迁移按新元数据建表的空库为空操作。

Revision ID: 0014_default_monitor_probe_mode
Revises: 0013_add_monitor_probe_interval
Create Date: 2026-10-23
"""

import sqlalchemy as sa
from alembic import op

revision = "0014_default_monitor_probe_mode"
down_revision = "0013_add_monitor_probe_interval"
branch_labels = None
depends_on = None

_TABLE = "monitor_traffic_settings"


def upgrade() -> None:
    """把监控模式列的数据库默认值改为 probe。"""

    inspector = sa.inspect(op.get_bind())
    if _TABLE not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns(_TABLE)}
    if "mode" not in columns:
        # 新库已按按类型拆分的列结构建表，不存在旧的 mode 列。
        return
    op.alter_column(
        _TABLE,
        "mode",
        existing_type=sa.String(length=16),
        server_default="probe",
        comment="监控数据模式：real 为用户真实请求，probe 为平台主动嗅探；默认 probe",
    )


def downgrade() -> None:
    """把监控模式列的数据库默认值恢复为 real。"""

    inspector = sa.inspect(op.get_bind())
    if _TABLE not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns(_TABLE)}
    if "mode" not in columns:
        return
    op.alter_column(
        _TABLE,
        "mode",
        existing_type=sa.String(length=16),
        server_default="real",
        comment="监控数据模式：real 为用户真实请求，probe 为平台主动嗅探",
    )
