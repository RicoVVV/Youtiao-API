"""记录视频任务最近一次向上游查询状态的时间。

Revision ID: 0016_add_video_last_polled_at
Revises: 0015_add_alert_notification_targets
Create Date: 2026-09-24

轮询任务与读请求共用同一时间戳：读请求触发的上游查询会让该任务在下一轮轮询中被跳过，
从而把同一任务的每次上游查询间隔收敛到一个调度周期。初始迁移按 ORM 元数据动态建表，
因此本迁移对表与列做存在性检查，既能用于已有库升级，也能在空库从头执行时不与初始迁移冲突。
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import Column, DateTime

revision = "0016_add_video_last_polled_at"
down_revision = "0015_add_alert_notification_targets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "video_tasks" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("video_tasks")}
    if "last_polled_at" not in columns:
        op.add_column("video_tasks", Column("last_polled_at", DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "video_tasks" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("video_tasks")}
    if "last_polled_at" in columns:
        op.drop_column("video_tasks", "last_polled_at")
