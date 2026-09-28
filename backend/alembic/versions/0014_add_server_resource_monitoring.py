"""新增服务器资源监控快照与资源告警阈值配置。

Revision ID: 0014_add_server_resource_monitoring
Revises: 0013_add_group_monitoring
Create Date: 2026-09-21

本迁移同时放开 ``monitor_alerts.group_id`` 的非空约束，使其可承载服务器资源告警，
并重建两个索引：裸列 ``group_id`` 在可空后会使 NULL 不参与唯一性判定，
导致同一资源指标重复插入活跃告警行。
初始迁移按 ORM 元数据动态建表，因此本迁移对全部对象做存在性检查，
既能用于已有库升级，也能在空库从头执行时不与初始迁移冲突。
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0014_add_server_resource_monitoring"
down_revision = "0013_add_group_monitoring"
branch_labels = None
depends_on = None

_RESOURCE_METRIC_VALUES = ("cpu_usage", "memory_usage", "swap_usage", "disk_usage")

_INDEX_DDL = (
    "CREATE INDEX IF NOT EXISTS ix_server_metric_snapshots_window_start ON server_metric_snapshots (window_start)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_server_metric_snapshots_window ON server_metric_snapshots (window_start)",
)

_ACTIVE_ALERT_INDEX_SQL = (
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_monitor_alerts_active"
    " ON monitor_alerts (COALESCE(group_id, 0),"
    " COALESCE(channel_id, '00000000-0000-0000-0000-000000000000'::uuid), metric)"
    " WHERE status IN ('pending', 'open') AND is_del = false"
)

_SCOPE_ALERT_INDEX_SQL = (
    "CREATE INDEX IF NOT EXISTS ix_monitor_alerts_scope"
    " ON monitor_alerts (COALESCE(group_id, 0), channel_id, metric, status)"
)

_LEGACY_ACTIVE_ALERT_INDEX_SQL = (
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_monitor_alerts_active"
    " ON monitor_alerts (group_id,"
    " COALESCE(channel_id, '00000000-0000-0000-0000-000000000000'::uuid), metric)"
    " WHERE status IN ('pending', 'open') AND is_del = false"
)

_LEGACY_SCOPE_ALERT_INDEX_SQL = (
    "CREATE INDEX IF NOT EXISTS ix_monitor_alerts_scope ON monitor_alerts (group_id, channel_id, metric, status)"
)


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    _add_metric_values(bind)
    _relax_alert_group_id(bind, tables)
    if "server_metric_snapshots" not in tables:
        _create_snapshot_table()
    if "monitor_resource_rules" not in tables:
        _create_resource_rule_table()
    for statement in _INDEX_DDL:
        bind.execute(sa.text(statement))
    if "monitor_alerts" in tables:
        bind.execute(sa.text("DROP INDEX IF EXISTS uq_monitor_alerts_active"))
        bind.execute(sa.text("DROP INDEX IF EXISTS ix_monitor_alerts_scope"))
        bind.execute(sa.text(_ACTIVE_ALERT_INDEX_SQL))
        bind.execute(sa.text(_SCOPE_ALERT_INDEX_SQL))


def downgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    for table_name in ("monitor_resource_rules", "server_metric_snapshots"):
        if table_name in tables:
            op.drop_table(table_name)
    if "monitor_alerts" not in tables:
        return
    # 恢复非空约束前必须先清除资源告警行，否则约束加不回去；枚举取值无法回滚。
    bind.execute(sa.text("DROP INDEX IF EXISTS uq_monitor_alerts_active"))
    bind.execute(sa.text("DROP INDEX IF EXISTS ix_monitor_alerts_scope"))
    bind.execute(sa.text("DELETE FROM monitor_alerts WHERE group_id IS NULL"))
    bind.execute(sa.text("ALTER TABLE monitor_alerts ALTER COLUMN group_id SET NOT NULL"))
    bind.execute(sa.text(_LEGACY_ACTIVE_ALERT_INDEX_SQL))
    bind.execute(sa.text(_LEGACY_SCOPE_ALERT_INDEX_SQL))


def _add_metric_values(bind) -> None:
    """向告警指标枚举追加资源类取值。

    PostgreSQL 枚举不支持删除取值，因此 downgrade 不回滚这三项；
    本迁移只追加取值、不使用新取值，避免在同一事务内引用刚加入的枚举值。
    """

    exists = bind.execute(sa.text("SELECT 1 FROM pg_type WHERE typname = 'monitor_alert_metric'")).scalar()
    if not exists:
        return
    for value in _RESOURCE_METRIC_VALUES:
        bind.execute(sa.text(f"ALTER TYPE monitor_alert_metric ADD VALUE IF NOT EXISTS '{value}'"))


def _relax_alert_group_id(bind, tables: set[str]) -> None:
    """放开告警表分组标识的非空约束，使其可承载服务器资源告警。"""

    if "monitor_alerts" not in tables:
        return
    nullable = bind.execute(
        sa.text(
            "SELECT is_nullable FROM information_schema.columns"
            " WHERE table_name = 'monitor_alerts' AND column_name = 'group_id'"
        )
    ).scalar()
    if nullable == "NO":
        bind.execute(sa.text("ALTER TABLE monitor_alerts ALTER COLUMN group_id DROP NOT NULL"))


def _base_columns() -> list[sa.Column]:
    """返回业务表共用的主键、逻辑删除与时间戳列。"""

    return [
        sa.Column("is_del", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    ]


def _create_snapshot_table() -> None:
    op.create_table(
        "server_metric_snapshots",
        *_base_columns(),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sample_interval_seconds", sa.Numeric(precision=12, scale=3), nullable=True),
        sa.Column("cpu_usage_percent", sa.Numeric(precision=7, scale=3), nullable=True),
        sa.Column("cpu_total_seconds", sa.Numeric(precision=20, scale=3), nullable=True),
        sa.Column("cpu_idle_seconds", sa.Numeric(precision=20, scale=3), nullable=True),
        sa.Column("cpu_core_count", sa.Integer(), nullable=False),
        sa.Column("cpu_per_core_percent", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("cpu_per_core_counters", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("load1", sa.Numeric(precision=12, scale=3), nullable=True),
        sa.Column("load5", sa.Numeric(precision=12, scale=3), nullable=True),
        sa.Column("load15", sa.Numeric(precision=12, scale=3), nullable=True),
        sa.Column("memory_total_bytes", sa.BigInteger(), nullable=True),
        sa.Column("memory_used_bytes", sa.BigInteger(), nullable=True),
        sa.Column("memory_usage_percent", sa.Numeric(precision=7, scale=3), nullable=True),
        sa.Column("swap_total_bytes", sa.BigInteger(), nullable=True),
        sa.Column("swap_used_bytes", sa.BigInteger(), nullable=True),
        sa.Column("swap_usage_percent", sa.Numeric(precision=7, scale=3), nullable=True),
        sa.Column(
            "network_interfaces",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "disks",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("max_disk_usage_percent", sa.Numeric(precision=7, scale=3), nullable=True),
        sa.Column("max_disk_mount", sa.String(length=512), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def _create_resource_rule_table() -> None:
    op.create_table(
        "monitor_resource_rules",
        *_base_columns(),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("cpu_usage_max", sa.Numeric(precision=7, scale=3), nullable=True),
        sa.Column("memory_usage_max", sa.Numeric(precision=7, scale=3), nullable=True),
        sa.Column("swap_usage_max", sa.Numeric(precision=7, scale=3), nullable=True),
        sa.Column("disk_usage_max", sa.Numeric(precision=7, scale=3), nullable=True),
        sa.Column("consecutive_hits", sa.Integer(), nullable=False, server_default="3"),
        sa.PrimaryKeyConstraint("id"),
    )
