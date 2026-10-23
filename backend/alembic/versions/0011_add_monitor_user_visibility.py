"""用户请求错误标记与用户侧监控可见范围配置。

- usage_records 增加 is_user_error，用于把用户请求内容/参数错误排除在监控统计之外；
- 新增 monitor_user_visibility 单行配置表，保存管理员允许用户看到的分组与请求类型；
- 全部对象使用存在性检查，由初始迁移按新元数据建表的空库为空操作。

Revision ID: 0011_add_monitor_user_visibility
Revises: 0010_add_channel_automation_settings
Create Date: 2026-10-23
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0011_add_monitor_user_visibility"
down_revision = "0010_add_channel_automation_settings"
branch_labels = None
depends_on = None

_USAGE_TABLE = "usage_records"
_USAGE_COLUMN = "is_user_error"
_VISIBILITY_TABLE = "monitor_user_visibility"


def upgrade() -> None:
    """补充用户错误标记列与用户侧监控可见范围配置表。"""

    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if _USAGE_TABLE in tables:
        columns = {column["name"] for column in inspector.get_columns(_USAGE_TABLE)}
        if _USAGE_COLUMN not in columns:
            op.add_column(
                _USAGE_TABLE,
                sa.Column(
                    _USAGE_COLUMN,
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.text("false"),
                    comment="是否由用户请求内容或参数触发的上游错误，此类请求不进入监控统计",
                ),
            )
    if _VISIBILITY_TABLE not in tables:
        op.create_table(
            _VISIBILITY_TABLE,
            sa.Column("is_del", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column(
                "enabled",
                sa.Boolean(),
                nullable=False,
                server_default="false",
                comment="是否限制用户侧监控可见范围，false 表示可见全部分组与请求类型",
            ),
            sa.Column(
                "group_ids",
                postgresql.JSONB(),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
                comment="开启限制后允许用户看到的分组标识列表",
            ),
            sa.Column(
                "request_types",
                postgresql.JSONB(),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
                comment="开启限制后允许用户看到的请求类型列表",
            ),
            sa.PrimaryKeyConstraint("id"),
        )


def downgrade() -> None:
    """移除用户侧监控可见范围配置表与用户错误标记列。"""

    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if _VISIBILITY_TABLE in tables:
        op.drop_table(_VISIBILITY_TABLE)
    if _USAGE_TABLE in tables:
        columns = {column["name"] for column in inspector.get_columns(_USAGE_TABLE)}
        if _USAGE_COLUMN in columns:
            op.drop_column(_USAGE_TABLE, _USAGE_COLUMN)
