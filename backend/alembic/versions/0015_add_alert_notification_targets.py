"""拆分推送开关并新增告警 @ 目标配置。

Revision ID: 0015_add_alert_notification_targets
Revises: 0014_add_server_resource_monitoring
Create Date: 2026-09-21

推送开关由单一 ``enabled`` 拆分为分组业务告警与服务器资源告警两个开关，
旧值按原状态回填到两个新开关后删除旧列；告警规则表新增 @ 手机号与 @ 所有人配置。
初始迁移按 ORM 元数据动态建表，因此本迁移对全部对象做存在性检查，
既能用于已有库升级，也能在空库从头执行时不与初始迁移冲突。
"""

import sqlalchemy as sa
from alembic import op

revision = "0015_add_alert_notification_targets"
down_revision = "0014_add_server_resource_monitoring"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "monitor_notification" in tables:
        _add_column(
            bind,
            "monitor_notification",
            sa.Column("notify_group_alerts", sa.Boolean(), nullable=False, server_default="false"),
        )
        _add_column(
            bind,
            "monitor_notification",
            sa.Column("notify_resource_alerts", sa.Boolean(), nullable=False, server_default="false"),
        )
        _split_legacy_enabled(bind)
    if "monitor_alert_rules" in tables:
        _add_column(
            bind,
            "monitor_alert_rules",
            sa.Column("at_mobiles", sa.String(length=512), nullable=False, server_default=""),
        )
        _add_column(
            bind,
            "monitor_alert_rules",
            sa.Column("at_all", sa.Boolean(), nullable=False, server_default="false"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "monitor_alert_rules" in tables:
        _drop_column(bind, "monitor_alert_rules", "at_all")
        _drop_column(bind, "monitor_alert_rules", "at_mobiles")
    if "monitor_notification" in tables:
        _add_column(
            bind, "monitor_notification", sa.Column("enabled", sa.Boolean(), nullable=False, server_default="false")
        )
        bind.execute(sa.text("UPDATE monitor_notification SET enabled = notify_group_alerts OR notify_resource_alerts"))
        _drop_column(bind, "monitor_notification", "notify_resource_alerts")
        _drop_column(bind, "monitor_notification", "notify_group_alerts")


def _split_legacy_enabled(bind) -> None:
    """把旧的统一开关回填到两个新开关并删除旧列；新库没有旧列时直接跳过。"""

    if "enabled" not in _columns(bind, "monitor_notification"):
        return
    bind.execute(
        sa.text("UPDATE monitor_notification SET notify_group_alerts = enabled, notify_resource_alerts = enabled")
    )
    op.drop_column("monitor_notification", "enabled")


def _add_column(bind, table: str, column: sa.Column) -> None:
    """按存在性检查补齐缺失列，兼容由初始迁移建出的新库。"""

    if column.name in _columns(bind, table):
        return
    op.add_column(table, column)


def _drop_column(bind, table: str, column: str) -> None:
    """按存在性检查删除列。"""

    if column not in _columns(bind, table):
        return
    op.drop_column(table, column)


def _columns(bind, table: str) -> set[str]:
    """读取表当前列名集合，表不存在时返回空集合。"""

    inspector = sa.inspect(bind)
    if table not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns(table)}
