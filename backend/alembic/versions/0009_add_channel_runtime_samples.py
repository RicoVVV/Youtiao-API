"""新增渠道运行时趋势采样表。

- 按渠道与分钟桶保存有效权重、成功率、平均耗时、熔断状态与启用状态；
- 使用存在性守卫：由初始迁移按新元数据建表的空库，本迁移为空操作。

Revision ID: 0009_add_channel_runtime_samples
Revises: 0008_add_channel_auto_disabled_at
Create Date: 2026-10-22
"""

import sqlalchemy as sa
from alembic import op
from app.bootstrap.model_registry import load_models
from app.core.database import SQLModelBase

revision = "0009_add_channel_runtime_samples"
down_revision = "0008_add_channel_auto_disabled_at"
branch_labels = None
depends_on = None

_NEW_TABLES = ("channel_runtime_samples",)


def upgrade() -> None:
    """仅创建缺失对象；新库初始迁移已按 ORM 元数据建表时此处为空操作。"""

    bind = op.get_bind()
    load_models()
    for table_name in _NEW_TABLES:
        table = SQLModelBase.metadata.tables.get(table_name)
        if table is not None:
            table.create(bind, checkfirst=True)


def downgrade() -> None:
    """移除渠道运行时趋势采样表。"""

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table_name in reversed(_NEW_TABLES):
        if inspector.has_table(table_name):
            op.drop_table(table_name)
