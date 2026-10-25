"""用量明细增加创建时间索引，支撑按时间跨度的统计查询与保留期清理。

- usage_records 增加 ix_usage_records_created_at；
- usage_records 增加仅覆盖仍带响应体记录的部分索引 ix_usage_records_pending_response；
- 使用存在性检查，由初始迁移按新元数据建表的空库为空操作。

Revision ID: 0016_add_usage_record_created_at_index
Revises: 0015_split_monitor_mode_by_type
Create Date: 2026-10-25
"""

import sqlalchemy as sa
from alembic import op

revision = "0016_add_usage_record_created_at_index"
down_revision = "0015_split_monitor_mode_by_type"
branch_labels = None
depends_on = None

_TABLE = "usage_records"
_CREATED_AT_INDEX = "ix_usage_records_created_at"
_PENDING_RESPONSE_INDEX = "ix_usage_records_pending_response"
_PENDING_RESPONSE_WHERE = sa.text("public_response_payload IS NOT NULL OR upstream_response_payload IS NOT NULL")


def upgrade() -> None:
    """创建按创建时间检索的索引与待清理响应体的部分索引。"""

    inspector = sa.inspect(op.get_bind())
    if _TABLE not in inspector.get_table_names():
        return
    existing = {index["name"] for index in inspector.get_indexes(_TABLE)}
    # usage_records 是大表：并发建索引避免发布时阻塞写入，因此必须在 Alembic 事务之外执行。
    with op.get_context().autocommit_block():
        if _CREATED_AT_INDEX not in existing:
            op.create_index(_CREATED_AT_INDEX, _TABLE, ["created_at"], postgresql_concurrently=True)
        if _PENDING_RESPONSE_INDEX not in existing:
            op.create_index(
                _PENDING_RESPONSE_INDEX,
                _TABLE,
                ["created_at"],
                postgresql_concurrently=True,
                postgresql_where=_PENDING_RESPONSE_WHERE,
            )


def downgrade() -> None:
    """移除创建时间索引与部分索引。"""

    inspector = sa.inspect(op.get_bind())
    if _TABLE not in inspector.get_table_names():
        return
    existing = {index["name"] for index in inspector.get_indexes(_TABLE)}
    with op.get_context().autocommit_block():
        if _PENDING_RESPONSE_INDEX in existing:
            op.drop_index(_PENDING_RESPONSE_INDEX, table_name=_TABLE, postgresql_concurrently=True)
        if _CREATED_AT_INDEX in existing:
            op.drop_index(_CREATED_AT_INDEX, table_name=_TABLE, postgresql_concurrently=True)
