"""创建删库重建所需的完整初始数据库结构及 Token 状态字段。

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-09-01
"""

from alembic import op
from app.bootstrap.model_registry import load_models
from sqlalchemy import text
from sqlmodel import SQLModel

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """根据当前 ORM 元数据创建全部业务表、约束、索引与逻辑删除字段。"""

    load_models()
    bind = op.get_bind()
    SQLModel.metadata.create_all(bind=bind)
    if bind.dialect.name == "postgresql":
        bind.execute(
            text(
                "INSERT INTO token_groups (name, visibility, is_active, is_default, is_del) "
                "SELECT 'default', 'public', true, true, false "
                "WHERE NOT EXISTS ("
                "SELECT 1 FROM token_groups WHERE name = 'default' AND is_del = false"
                ")"
            )
        )


def downgrade() -> None:
    """删除初始迁移创建的全部业务表，仅用于本地重建场景。"""

    load_models()
    SQLModel.metadata.drop_all(bind=op.get_bind())
