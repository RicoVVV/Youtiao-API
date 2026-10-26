"""回填已注销用户的占位登录名，释放原用户名供重新注册。

Revision ID: 0019_backfill_deleted_usernames
Revises: 0018_affiliate_default_values
Create Date: 2026-10-26
"""

import sqlalchemy as sa
from alembic import op

revision = "0019_backfill_deleted_usernames"
down_revision = "0018_affiliate_default_values"
branch_labels = None
depends_on = None

# 占位名保留原名前 115 个字符并附加 id 前缀，确保总长度不超 users.username 的 128 上限。
_PLACEHOLDER_USERNAME = "left(u.username, 115) || '-del-' || left(u.id::text, 8)"


def upgrade() -> None:
    """把已注销用户登录名改写为占位名；已被占用的目标名跳过，保证迁移幂等可重复执行。"""

    op.execute(
        sa.text(
            f"""
            UPDATE users AS u
            SET username = {_PLACEHOLDER_USERNAME}
            WHERE u.is_del = true
              AND u.username <> {_PLACEHOLDER_USERNAME}
              AND NOT EXISTS (
                SELECT 1
                FROM users AS o
                WHERE o.id <> u.id
                  AND o.username = {_PLACEHOLDER_USERNAME}
              )
            """
        )
    )


def downgrade() -> None:
    """无法安全还原被释放的原用户名，保持不变以避免与已重新注册的用户冲突。"""
