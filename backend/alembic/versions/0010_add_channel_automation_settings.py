"""为系统设置增加渠道探测与自动禁用配置列。

- system_settings 增加定时探测开关、间隔、超时、自动禁用/启用开关、状态码与关键词；
- 使用存在性检查，由初始迁移按新元数据建表的空库为空操作。

Revision ID: 0010_add_channel_automation_settings
Revises: 0009_add_channel_runtime_samples
Create Date: 2026-10-23
"""

import sqlalchemy as sa
from alembic import op

revision = "0010_add_channel_automation_settings"
down_revision = "0009_add_channel_runtime_samples"
branch_labels = None
depends_on = None

_TABLE = "system_settings"
_DEFAULT_KEYWORDS = "\n".join(
    (
        "Your credit balance is too low",
        "This organization has been disabled.",
        "You exceeded your current quota",
        "Permission denied",
        "The security token included in the request is invalid",
        "Operation not allowed",
        "Your account is not authorized",
        "unknown provider for model",
        "The usage limit has been reached",
        "预扣费额度失败",
        "Insufficient account balance",
        "no auth available",
    )
)

_COLUMNS = (
    (
        "channel_probe_enabled",
        sa.Column(
            "channel_probe_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="是否定时探测所有渠道",
        ),
    ),
    (
        "channel_probe_interval_minutes",
        sa.Column(
            "channel_probe_interval_minutes",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
            comment="定时探测所有渠道的间隔分钟数",
        ),
    ),
    (
        "channel_probe_timeout_seconds",
        sa.Column(
            "channel_probe_timeout_seconds",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("5"),
            comment="单次渠道探测的最长响应秒数",
        ),
    ),
    (
        "channel_auto_disable_enabled",
        sa.Column(
            "channel_auto_disable_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="失败时是否自动禁用渠道",
        ),
    ),
    (
        "channel_auto_enable_enabled",
        sa.Column(
            "channel_auto_enable_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
            comment="成功后是否自动启用渠道",
        ),
    ),
    (
        "channel_auto_disable_status_codes",
        sa.Column(
            "channel_auto_disable_status_codes",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'401,429'"),
            comment="触发自动禁用的上游状态码，逗号分隔，支持起止范围",
        ),
    ),
    (
        "channel_auto_retry_status_codes",
        sa.Column(
            "channel_auto_retry_status_codes",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'100-199,300-399,401-407,409-499,500-503,505-523,525-599'"),
            comment="允许自动重试的上游状态码，逗号分隔，支持起止范围；504 与 524 始终不重试",
        ),
    ),
    (
        "channel_auto_disable_keywords",
        sa.Column(
            "channel_auto_disable_keywords",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'" + _DEFAULT_KEYWORDS.replace("'", "''") + "'"),
            comment="触发自动禁用的上游错误关键词，换行分隔，不区分大小写",
        ),
    ),
)


def upgrade() -> None:
    """为系统设置表补充渠道自动化配置列。"""

    inspector = sa.inspect(op.get_bind())
    if _TABLE not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns(_TABLE)}
    for name, column in _COLUMNS:
        if name not in existing:
            op.add_column(_TABLE, column)


def downgrade() -> None:
    """移除系统设置表的渠道自动化配置列。"""

    inspector = sa.inspect(op.get_bind())
    if _TABLE not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns(_TABLE)}
    for name, _column in reversed(_COLUMNS):
        if name in existing:
            op.drop_column(_TABLE, name)
