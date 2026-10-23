"""分组监控嗅探模式：快照增加模式维度并新增嗅探结果与模式配置表。

- group_metric_snapshots 增加 mode，唯一索引改为按「窗口 × 分组 × 类型 × 模式」去重；
- 新增 group_probe_results 保存平台主动发送的最小文本嗅探结果；
- 新增 monitor_traffic_settings 单行配置保存全局统一的监控模式；
- 全部对象使用存在性检查，由初始迁移按新元数据建表的空库为空操作。

Revision ID: 0012_add_group_monitor_probe
Revises: 0011_add_monitor_user_visibility
Create Date: 2026-10-23
"""

import sqlalchemy as sa
from alembic import op

revision = "0012_add_group_monitor_probe"
down_revision = "0011_add_monitor_user_visibility"
branch_labels = None
depends_on = None

_SNAPSHOT_TABLE = "group_metric_snapshots"
_TRAFFIC_SETTING_TABLE = "monitor_traffic_settings"
_PROBE_TABLE = "group_probe_results"
_OLD_UNIQUE_INDEX = "uq_group_metric_snapshots_window_group_type"
_NEW_UNIQUE_INDEX = "uq_group_metric_snapshots_window_group_type_mode"


def upgrade() -> None:
    """补充监控模式、嗅探结果表与快照模式维度。"""

    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if _SNAPSHOT_TABLE in tables:
        columns = {column["name"] for column in inspector.get_columns(_SNAPSHOT_TABLE)}
        if "mode" not in columns:
            op.add_column(
                _SNAPSHOT_TABLE,
                sa.Column(
                    "mode",
                    sa.String(length=16),
                    nullable=False,
                    server_default="real",
                    comment="数据模式：real 为用户真实请求，probe 为平台主动嗅探",
                ),
            )
            op.create_index(
                "ix_group_metric_snapshots_mode",
                _SNAPSHOT_TABLE,
                ["mode"],
            )
        op.execute(f"DROP INDEX IF EXISTS {_OLD_UNIQUE_INDEX}")
        op.execute(
            f"CREATE UNIQUE INDEX IF NOT EXISTS {_NEW_UNIQUE_INDEX}"
            f" ON {_SNAPSHOT_TABLE} (window_start, token_group_id, request_type, mode)"
        )
    if _TRAFFIC_SETTING_TABLE not in tables:
        op.create_table(
            _TRAFFIC_SETTING_TABLE,
            sa.Column("is_del", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column(
                "mode",
                sa.String(length=16),
                nullable=False,
                server_default="real",
                comment="监控数据模式：real 为用户真实请求，probe 为平台主动嗅探",
            ),
            sa.PrimaryKeyConstraint("id"),
        )
    if _PROBE_TABLE not in tables:
        op.create_table(
            _PROBE_TABLE,
            sa.Column("is_del", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("token_group_id", sa.Integer(), nullable=False),
            sa.Column("model_id", sa.Uuid(), nullable=True),
            sa.Column("model_name", sa.String(length=64), nullable=False),
            sa.Column("channel_id", sa.Uuid(), nullable=True),
            sa.Column("channel_name", sa.String(length=128), nullable=True),
            sa.Column("provider_name", sa.String(length=64), nullable=False),
            sa.Column("request_type", sa.String(length=64), nullable=False, server_default="text"),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("duration_ms", sa.Integer(), nullable=False),
            sa.Column("first_token_duration_ms", sa.Integer(), nullable=True),
            sa.Column("error_code", sa.String(length=64), nullable=True),
            sa.Column("error_message", sa.String(length=512), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(["token_group_id"], ["token_groups.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["model_id"], ["models.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["channel_id"], ["channels.id"], ondelete="SET NULL"),
        )
        op.create_index("ix_group_probe_results_completed_at", _PROBE_TABLE, ["completed_at"])
        op.create_index(
            "ix_group_probe_results_group_completed",
            _PROBE_TABLE,
            ["token_group_id", "completed_at"],
        )
        op.create_index("ix_group_probe_results_token_group_id", _PROBE_TABLE, ["token_group_id"])
        op.create_index("ix_group_probe_results_model_id", _PROBE_TABLE, ["model_id"])
        op.create_index("ix_group_probe_results_channel_id", _PROBE_TABLE, ["channel_id"])


def downgrade() -> None:
    """移除嗅探模式相关表与快照模式维度。"""

    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if _PROBE_TABLE in tables:
        op.drop_table(_PROBE_TABLE)
    if _TRAFFIC_SETTING_TABLE in tables:
        op.drop_table(_TRAFFIC_SETTING_TABLE)
    if _SNAPSHOT_TABLE in tables:
        op.execute(f"DROP INDEX IF EXISTS {_NEW_UNIQUE_INDEX}")
        op.execute("DROP INDEX IF EXISTS ix_group_metric_snapshots_mode")
        columns = {column["name"] for column in inspector.get_columns(_SNAPSHOT_TABLE)}
        if "mode" in columns:
            # 回退到单模式唯一索引前必须清理嗅探快照，否则同一窗口会出现重复键。
            op.execute(f"DELETE FROM {_SNAPSHOT_TABLE} WHERE mode = 'probe'")
            op.drop_column(_SNAPSHOT_TABLE, "mode")
        op.execute(
            f"CREATE UNIQUE INDEX IF NOT EXISTS {_OLD_UNIQUE_INDEX}"
            f" ON {_SNAPSHOT_TABLE} (window_start, token_group_id, request_type)"
        )
