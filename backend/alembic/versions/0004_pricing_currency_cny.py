"""将定价规则默认币种统一为人民币 CNY。

- 调整 ``pricing_rules.currency`` 的数据库默认值；
- 把存量定价规则的币种统一改写为 CNY，与钱包、充值和会员套餐的人民币记账口径保持一致；
- 带表存在性检查，由初始迁移按新元数据建表的空库可重复执行。

Revision ID: 0004_pricing_currency_cny
Revises: 0003_membership_sidebar
Create Date: 2026-10-20
"""

import sqlalchemy as sa
from alembic import op

revision = "0004_pricing_currency_cny"
down_revision = "0003_membership_sidebar"
branch_labels = None
depends_on = None

_TABLE = "pricing_rules"


def upgrade() -> None:
    """把定价规则默认币种与存量数据统一为 CNY。"""

    _set_currency_default("CNY")
    _normalize_existing_currency("CNY")


def downgrade() -> None:
    """恢复默认币种为 USD；不回写存量数据，避免覆盖已有币种信息。"""

    _set_currency_default("USD")


def _set_currency_default(default: str) -> None:
    inspector = sa.inspect(op.get_bind())
    if _TABLE not in inspector.get_table_names():
        return
    op.alter_column(_TABLE, "currency", existing_type=sa.String(length=8), server_default=default)


def _normalize_existing_currency(currency: str) -> None:
    inspector = sa.inspect(op.get_bind())
    if _TABLE not in inspector.get_table_names():
        return
    rules = sa.table(_TABLE, sa.column("currency", sa.String(length=8)))
    op.execute(rules.update().where(rules.c.currency != currency).values(currency=currency))
