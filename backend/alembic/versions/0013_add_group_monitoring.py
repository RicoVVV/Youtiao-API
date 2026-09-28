"""新增分组监控与告警相关表结构。

Revision ID: 0013_add_group_monitoring
Revises: 0012_add_model_description
Create Date: 2026-09-21

初始迁移按 ORM 元数据动态建表，因此本迁移对全部对象做存在性检查，
既能用于已有库补齐新表，也能在空库执行时不与初始迁移冲突。
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0013_add_group_monitoring"
down_revision = "0012_add_model_description"
branch_labels = None
depends_on = None

_ALERT_METRIC_VALUES = ("success_rate", "average_duration_ms", "average_first_token_ms")
_ALERT_STATUS_VALUES = ("pending", "open", "resolved", "acknowledged", "ignored")
_ALERT_NOTIFICATION_VALUES = ("pending", "sent", "failed", "skipped")

_INDEX_DDL = (
    "CREATE INDEX IF NOT EXISTS ix_group_metric_snapshots_window_start ON group_metric_snapshots (window_start)",
    "CREATE INDEX IF NOT EXISTS ix_group_metric_snapshots_token_group_id ON group_metric_snapshots (token_group_id)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_group_metric_snapshots_window_group_type"
    " ON group_metric_snapshots (window_start, token_group_id, request_type)",
    "CREATE INDEX IF NOT EXISTS ix_group_metric_snapshots_group_window"
    " ON group_metric_snapshots (token_group_id, window_start)",
    "CREATE INDEX IF NOT EXISTS ix_monitor_alert_rules_group_id ON monitor_alert_rules (group_id)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_monitor_alert_rules_scope"
    " ON monitor_alert_rules (COALESCE(group_id, 0)) WHERE is_del = false",
    "CREATE INDEX IF NOT EXISTS ix_monitor_alerts_group_id ON monitor_alerts (group_id)",
    "CREATE INDEX IF NOT EXISTS ix_monitor_alerts_channel_id ON monitor_alerts (channel_id)",
    "CREATE INDEX IF NOT EXISTS ix_monitor_alerts_status ON monitor_alerts (status)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_monitor_alerts_active"
    " ON monitor_alerts (group_id,"
    " COALESCE(channel_id, '00000000-0000-0000-0000-000000000000'::uuid), metric)"
    " WHERE status IN ('pending', 'open') AND is_del = false",
    "CREATE INDEX IF NOT EXISTS ix_monitor_alerts_scope ON monitor_alerts (group_id, channel_id, metric, status)",
    "CREATE INDEX IF NOT EXISTS ix_monitor_alerts_status_updated ON monitor_alerts (status, updated_at)",
    "CREATE INDEX IF NOT EXISTS ix_usage_records_completed_at ON usage_records (completed_at)",
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    _create_enum(bind, "monitor_alert_metric", _ALERT_METRIC_VALUES)
    _create_enum(bind, "monitor_alert_status", _ALERT_STATUS_VALUES)
    _create_enum(bind, "monitor_alert_notification_status", _ALERT_NOTIFICATION_VALUES)
    if "group_metric_snapshots" not in tables:
        _create_snapshot_table()
    if "monitor_alert_rules" not in tables:
        _create_alert_rule_table()
    if "monitor_notification" not in tables:
        _create_notification_table()
    if "monitor_alerts" not in tables:
        _create_alert_table()
    for statement in _INDEX_DDL:
        bind.execute(sa.text(statement))


def downgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "usage_records" in tables:
        bind.execute(sa.text("DROP INDEX IF EXISTS ix_usage_records_completed_at"))
    for table_name in ("monitor_alerts", "monitor_notification", "monitor_alert_rules", "group_metric_snapshots"):
        if table_name in tables:
            op.drop_table(table_name)
    for enum_name in ("monitor_alert_notification_status", "monitor_alert_status", "monitor_alert_metric"):
        bind.execute(sa.text(f"DROP TYPE IF EXISTS {enum_name}"))


def _create_enum(bind, enum_name: str, values: tuple[str, ...]) -> None:
    """按 PostgreSQL 枚举类型创建缺失的类型定义。"""

    exists = bind.execute(sa.text("SELECT 1 FROM pg_type WHERE typname = :name"), {"name": enum_name}).scalar()
    if exists:
        return
    literals = ", ".join(f"'{value}'" for value in values)
    bind.execute(sa.text(f"CREATE TYPE {enum_name} AS ENUM ({literals})"))


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
        "group_metric_snapshots",
        *_base_columns(),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("token_group_id", sa.Integer(), nullable=False),
        sa.Column("request_type", sa.String(length=64), nullable=False),
        sa.Column("succeeded_count", sa.Integer(), nullable=False),
        sa.Column("failed_count", sa.Integer(), nullable=False),
        sa.Column("refunded_count", sa.Integer(), nullable=False),
        sa.Column("total_duration_ms", sa.BigInteger(), nullable=False),
        sa.Column("first_token_sum_ms", sa.BigInteger(), nullable=False),
        sa.Column("first_token_count", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["token_group_id"], ["token_groups.id"], ondelete="RESTRICT"),
    )


def _create_alert_rule_table() -> None:
    op.create_table(
        "monitor_alert_rules",
        *_base_columns(),
        sa.Column("group_id", sa.Integer(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("success_rate_min", sa.Numeric(precision=6, scale=4), nullable=True),
        sa.Column("avg_duration_ms_max", sa.Integer(), nullable=True),
        sa.Column("avg_first_token_ms_max", sa.Integer(), nullable=True),
        sa.Column("min_sample_count", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("consecutive_hits", sa.Integer(), nullable=False, server_default="2"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["group_id"], ["token_groups.id"], ondelete="RESTRICT"),
    )


def _create_notification_table() -> None:
    op.create_table(
        "monitor_notification",
        *_base_columns(),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("webhook_url", sa.String(length=2048), nullable=False, server_default=""),
        sa.Column("sign_secret", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("keyword", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("silence_minutes", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("notify_on_resolved", sa.Boolean(), nullable=False, server_default="false"),
        sa.PrimaryKeyConstraint("id"),
    )


def _create_alert_table() -> None:
    op.create_table(
        "monitor_alerts",
        *_base_columns(),
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.Column("channel_id", sa.Uuid(), nullable=True),
        sa.Column(
            "metric",
            postgresql.ENUM(*_ALERT_METRIC_VALUES, name="monitor_alert_metric", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "status",
            postgresql.ENUM(*_ALERT_STATUS_VALUES, name="monitor_alert_status", create_type=False),
            nullable=False,
        ),
        sa.Column("first_window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("actual_value", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("threshold_value", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("consecutive_hits", sa.Integer(), nullable=False),
        sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "notification_status",
            postgresql.ENUM(*_ALERT_NOTIFICATION_VALUES, name="monitor_alert_notification_status", create_type=False),
            nullable=False,
        ),
        sa.Column("notification_error", sa.String(length=512), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["group_id"], ["token_groups.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["channel_id"], ["channels.id"], ondelete="RESTRICT"),
    )
