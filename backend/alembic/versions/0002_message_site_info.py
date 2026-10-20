"""新增站内消息、通知与站点信息表。

Revision ID: 0002_message_site_info
Revises: 0001_initial_schema
Create Date: 2026-10-19
"""

from alembic import op
from app.bootstrap.model_registry import load_models
from sqlmodel import SQLModel

revision = "0002_message_site_info"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None

_NEW_TABLES = (
    "site_info",
    "messages",
    "message_targets",
    "message_reads",
    "notifications",
    "notification_targets",
    "notification_dismissals",
)


def upgrade() -> None:
    """按当前 ORM 元数据创建消息、通知与站点信息相关表。"""

    load_models()
    SQLModel.metadata.create_all(
        bind=op.get_bind(),
        tables=[SQLModel.metadata.tables[name] for name in _NEW_TABLES],
    )


def downgrade() -> None:
    """删除本次迁移新增的消息、通知与站点信息表。"""

    load_models()
    SQLModel.metadata.drop_all(
        bind=op.get_bind(),
        tables=[SQLModel.metadata.tables[name] for name in _NEW_TABLES],
    )
