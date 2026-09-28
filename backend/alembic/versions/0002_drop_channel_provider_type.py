"""删除渠道表的适配器类型列。

渠道只保留上游连接与选路配置，请求协议由模型模板决定，因此移除渠道侧的适配器标识。
初始迁移按 ORM 元数据建表，新库不会创建该列，本迁移对已存在的旧库使用存在性检查保证幂等。

Revision ID: 0002_drop_channel_provider_type
Revises: 0001_initial_schema
Create Date: 2026-09-12
"""

from alembic import op
from sqlalchemy import Column, String, inspect

revision = "0002_drop_channel_provider_type"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """存在该列时删除渠道适配器类型列，新旧数据库均可重复执行。"""

    bind = op.get_bind()
    if "channels" not in inspect(bind).get_table_names():
        return
    columns = {column["name"] for column in inspect(bind).get_columns("channels")}
    if "provider_type" in columns:
        op.drop_column("channels", "provider_type")


def downgrade() -> None:
    """恢复渠道适配器类型列，历史逐行数据无法还原。"""

    bind = op.get_bind()
    if "channels" not in inspect(bind).get_table_names():
        return
    columns = {column["name"] for column in inspect(bind).get_columns("channels")}
    if "provider_type" not in columns:
        op.add_column("channels", Column("provider_type", String(32), nullable=False, server_default=""))
