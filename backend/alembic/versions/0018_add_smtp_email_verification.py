"""为系统设置增加注册邮箱验证开关与 SMTP 发信配置，兼容初始迁移动态建表。

Revision ID: 0018_add_smtp_email_verification
Revises: 0017_add_user_email
"""

import sqlalchemy as sa
from alembic import op

revision = "0018_add_smtp_email_verification"
down_revision = "0017_add_user_email"
branch_labels = None
depends_on = None

_TABLE = "system_settings"


def _columns() -> list[sa.Column]:
    return [
        sa.Column("email_verification_enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("smtp_host", sa.String(255), nullable=False, server_default=""),
        sa.Column("smtp_port", sa.Integer(), nullable=False, server_default="587"),
        sa.Column("smtp_security", sa.String(16), nullable=False, server_default="starttls"),
        sa.Column("smtp_username", sa.String(320), nullable=False, server_default=""),
        sa.Column("smtp_password_ciphertext", sa.Text(), nullable=False, server_default=""),
        sa.Column("smtp_from_email", sa.String(320), nullable=False, server_default=""),
        sa.Column("smtp_from_name", sa.String(255), nullable=False, server_default=""),
    ]


def upgrade() -> None:
    """仅添加缺失列；新库初始迁移已按 ORM 元数据建列时不重复添加。"""

    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    existing = {column["name"] for column in inspector.get_columns(_TABLE)}
    for column in _columns():
        if column.name not in existing:
            op.add_column(_TABLE, column)


def downgrade() -> None:
    """移除新增列；回退会清除已保存的 SMTP 配置与邮箱验证开关。"""

    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    existing = {column["name"] for column in inspector.get_columns(_TABLE)}
    for column in reversed(_columns()):
        if column.name in existing:
            op.drop_column(_TABLE, column.name)
