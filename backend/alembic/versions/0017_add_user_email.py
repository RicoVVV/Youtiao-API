"""为用户增加已验证邮箱字段，供注册邮箱验证记录发信邮箱，兼容初始迁移动态建表。

Revision ID: 0017_add_user_email
Revises: 0016_add_video_last_polled_at
"""

import sqlalchemy as sa
from alembic import op

revision = "0017_add_user_email"
down_revision = "0016_add_video_last_polled_at"
branch_labels = None
depends_on = None

_TABLE = "users"


def upgrade() -> None:
    """仅添加缺失列；新库初始迁移已按 ORM 元数据建列时不重复添加。"""

    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns(_TABLE)}
    if "email" not in columns:
        op.add_column(
            _TABLE,
            sa.Column("email", sa.String(320), nullable=True, comment="注册验证通过后的邮箱"),
        )


def downgrade() -> None:
    """移除邮箱列；回退会清除已保存的验证邮箱资料。"""

    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns(_TABLE)}
    if "email" in columns:
        op.drop_column(_TABLE, "email")
