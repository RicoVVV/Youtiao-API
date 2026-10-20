"""新增会员系统与侧边栏模块可见性。

- 新建会员等级、套餐、专享分组、用户会员与会员流水表；
- 扩展在线充值订单的订单类型与会员套餐关联、余额流水的会员流水关联；
- 系统设置增加侧边栏可见性覆盖列；
- 新库由初始迁移按 ORM 元数据建表，本迁移通过存在性检查做到可重复执行。

Revision ID: 0003_membership_sidebar
Revises: 0002_message_site_info
Create Date: 2026-10-20
"""

from uuid import uuid4

import sqlalchemy as sa
from alembic import op
from app.bootstrap.model_registry import load_models
from sqlalchemy.dialects import postgresql
from sqlmodel import SQLModel

revision = "0003_membership_sidebar"
down_revision = "0002_message_site_info"
branch_labels = None
depends_on = None

_NEW_TABLES = (
    "membership_levels",
    "membership_plans",
    "membership_level_groups",
    "user_memberships",
    "membership_records",
)
_RECHARGE_ORDER_TYPE = postgresql.ENUM("recharge", "membership", name="recharge_order_type", create_type=False)
_SEED_LEVELS = (
    {"code": "vip", "name": "VIP", "rank": 1},
    {"code": "svip", "name": "SVIP", "rank": 2},
)


def _add_column_if_missing(inspector: sa.Inspector, table: str, column: sa.Column) -> None:
    if column.name not in {item["name"] for item in inspector.get_columns(table)}:
        op.add_column(table, column)


def _create_fk_if_missing(inspector: sa.Inspector, name: str, table: str, referent: str, column: str) -> None:
    """按约束列判断外键是否存在，兼容初始迁移按 ORM 默认命名创建的外键。"""

    if not any(item["constrained_columns"] == [column] for item in inspector.get_foreign_keys(table)):
        op.create_foreign_key(name, table, referent, [column], ["id"], ondelete="RESTRICT")


def _add_sidebar_visibility() -> None:
    inspector = sa.inspect(op.get_bind())
    if "system_settings" not in inspector.get_table_names():
        return
    if "sidebar_visibility" in {item["name"] for item in inspector.get_columns("system_settings")}:
        return
    op.add_column(
        "system_settings",
        sa.Column("sidebar_visibility", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )


def upgrade() -> None:
    """仅创建缺失对象并写入预置会员等级。"""

    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE balance_record_type ADD VALUE IF NOT EXISTS 'membership_bonus'")

    bind = op.get_bind()
    load_models()
    for table_name in _NEW_TABLES:
        SQLModel.metadata.tables[table_name].create(bind, checkfirst=True)

    _RECHARGE_ORDER_TYPE.create(bind, checkfirst=True)
    inspector = sa.inspect(bind)

    _add_column_if_missing(
        inspector,
        "recharge_orders",
        sa.Column("order_type", _RECHARGE_ORDER_TYPE, nullable=False, server_default="recharge"),
    )
    _add_column_if_missing(inspector, "recharge_orders", sa.Column("membership_plan_id", sa.Uuid(), nullable=True))
    _create_fk_if_missing(
        inspector, "fk_recharge_orders_membership_plan_id", "recharge_orders", "membership_plans", "membership_plan_id"
    )
    checks = {item["name"] for item in inspector.get_check_constraints("recharge_orders")}
    if "ck_recharge_orders_membership_plan" not in checks:
        op.create_check_constraint(
            "ck_recharge_orders_membership_plan",
            "recharge_orders",
            "(order_type = 'membership') = (membership_plan_id IS NOT NULL)",
        )

    _add_column_if_missing(inspector, "balance_records", sa.Column("membership_record_id", sa.Uuid(), nullable=True))
    _create_fk_if_missing(
        inspector,
        "fk_balance_records_membership_record_id",
        "balance_records",
        "membership_records",
        "membership_record_id",
    )
    indexes = {item["name"] for item in inspector.get_indexes("balance_records")}
    if "ix_balance_records_membership_record_id" not in indexes:
        op.create_index("ix_balance_records_membership_record_id", "balance_records", ["membership_record_id"])

    _add_sidebar_visibility()

    for level in _SEED_LEVELS:
        bind.execute(
            sa.text(
                "INSERT INTO membership_levels "
                "(id, code, name, description, rank, is_public, is_active, is_del) "
                "SELECT :id, CAST(:code AS varchar), :name, '', :rank, true, true, false "
                "WHERE NOT EXISTS ("
                "SELECT 1 FROM membership_levels WHERE code = CAST(:code AS varchar) AND is_del = false)"
            ),
            {"id": uuid4(), **level},
        )


def downgrade() -> None:
    """移除会员相关列、表与侧边栏可见性列；PostgreSQL 不支持删除枚举值，membership_bonus 保留。"""

    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "sidebar_visibility" in {item["name"] for item in inspector.get_columns("system_settings")}:
        op.drop_column("system_settings", "sidebar_visibility")

    if "membership_record_id" in {item["name"] for item in inspector.get_columns("balance_records")}:
        op.drop_column("balance_records", "membership_record_id")

    order_columns = {item["name"] for item in inspector.get_columns("recharge_orders")}
    checks = {item["name"] for item in inspector.get_check_constraints("recharge_orders")}
    if "ck_recharge_orders_membership_plan" in checks:
        op.drop_constraint("ck_recharge_orders_membership_plan", "recharge_orders", type_="check")
    if "membership_plan_id" in order_columns:
        op.drop_column("recharge_orders", "membership_plan_id")
    if "order_type" in order_columns:
        op.drop_column("recharge_orders", "order_type")
    _RECHARGE_ORDER_TYPE.drop(bind, checkfirst=True)

    for table_name in reversed(_NEW_TABLES):
        if inspector.has_table(table_name):
            op.drop_table(table_name)
    postgresql.ENUM(name="membership_record_source").drop(bind, checkfirst=True)
    postgresql.ENUM(name="membership_period").drop(bind, checkfirst=True)
