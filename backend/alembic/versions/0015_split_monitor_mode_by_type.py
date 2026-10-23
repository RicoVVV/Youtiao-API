"""把分组监控数据模式由全局单列拆分为按请求类型的独立配置。

- monitor_traffic_settings 增加 text_mode、image_mode、video_mode；
- 旧的 mode 列回填到 text_mode，image_mode 与 video_mode 固定默认 real；
- 删除旧的 mode 列；
- 全部操作使用存在性检查，由初始迁移按新元数据建表的空库为空操作。

Revision ID: 0015_split_monitor_mode_by_type
Revises: 0014_default_monitor_probe_mode
Create Date: 2026-10-23
"""

import sqlalchemy as sa
from alembic import op

revision = "0015_split_monitor_mode_by_type"
down_revision = "0014_default_monitor_probe_mode"
branch_labels = None
depends_on = None

_TABLE = "monitor_traffic_settings"
_OLD_COLUMN = "mode"
_NEW_COLUMNS = (
    ("text_mode", "文本请求数据模式：real 或 probe"),
    ("image_mode", "图片请求数据模式：固定 real"),
    ("video_mode", "视频请求数据模式：固定 real"),
)


def upgrade() -> None:
    """把单列监控模式拆分为按请求类型的三列。"""

    inspector = sa.inspect(op.get_bind())
    if _TABLE not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns(_TABLE)}
    if _OLD_COLUMN not in columns and all(name in columns for name, _ in _NEW_COLUMNS):
        # 新库已按按类型拆分的列结构建表，无需迁移。
        return
    for name, comment in _NEW_COLUMNS:
        if name in columns:
            continue
        op.add_column(
            _TABLE,
            sa.Column(
                name,
                sa.String(length=16),
                nullable=False,
                server_default="real",
                comment=comment,
            ),
        )
    if _OLD_COLUMN in columns:
        op.execute(f"UPDATE {_TABLE} SET text_mode = {_OLD_COLUMN} WHERE {_OLD_COLUMN} IN ('real', 'probe')")
        op.execute(f"UPDATE {_TABLE} SET image_mode = 'real', video_mode = 'real'")
        op.drop_column(_TABLE, _OLD_COLUMN)
    op.alter_column(
        _TABLE,
        "text_mode",
        existing_type=sa.String(length=16),
        server_default="probe",
        comment="文本请求数据模式：real 或 probe；默认 probe",
    )


def downgrade() -> None:
    """把按请求类型的监控模式合并回单列。"""

    inspector = sa.inspect(op.get_bind())
    if _TABLE not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns(_TABLE)}
    if _OLD_COLUMN not in columns:
        op.add_column(
            _TABLE,
            sa.Column(
                _OLD_COLUMN,
                sa.String(length=16),
                nullable=False,
                server_default="real",
                comment="监控数据模式：real 为用户真实请求，probe 为平台主动嗅探",
            ),
        )
        if "text_mode" in columns:
            op.execute(f"UPDATE {_TABLE} SET {_OLD_COLUMN} = text_mode")
    for name, _ in _NEW_COLUMNS:
        if name in columns:
            op.drop_column(_TABLE, name)
