"""Token 分组、用户授权和 Token 有序绑定的 ORM 映射。

本模块只保存分组可见范围、显式授权和凭证优先级关系；分组可用性与跨资源权限校验由应用服务负责。
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    func,
    text,
)
from sqlmodel import Field

from app.core.database import SQLModelBase


class TokenGroup(SQLModelBase, table=True):
    """保存管理员维护的 Token 渠道调度分组。"""

    __tablename__ = "token_groups"
    __table_args__ = (
        CheckConstraint("visibility IN ('public', 'restricted')", name="ck_token_groups_visibility"),
        CheckConstraint(
            "is_default = false OR (visibility = 'public' AND is_active = true)",
            name="ck_token_groups_default_public_active",
        ),
        CheckConstraint("price_multiplier > 0", name="ck_token_groups_price_multiplier_positive"),
        Index("uq_token_groups_name_active", "name", unique=True, postgresql_where=text("is_del = false")),
        Index(
            "uq_token_groups_default_active",
            "is_default",
            unique=True,
            postgresql_where=text("is_default = true AND is_del = false"),
        ),
    )

    id: int | None = Field(default=None, primary_key=True, description="数据库生成的 Token 分组自增主键")
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now(), comment="分组创建时间"),
    )
    name: str = Field(sa_column=Column(String(128), nullable=False, comment="管理员维护的唯一分组名称"))
    description: str = Field(
        default="",
        sa_column=Column(String(512), nullable=False, server_default="", comment="面向用户展示的分组介绍，可为空"),
    )
    visibility: str = Field(
        sa_column=Column(String(16), nullable=False, comment="public 全员可用，restricted 仅显式授权用户可用")
    )
    is_active: bool = Field(
        default=True,
        sa_column=Column(Boolean, nullable=False, server_default="true", comment="停用后不允许新的绑定和运行时使用"),
    )
    is_default: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default="false", comment="系统预置且不可变更的默认分组标识"),
    )
    price_multiplier: Decimal = Field(
        default=Decimal("1.000000"),
        sa_column=Column(
            Numeric(18, 6), nullable=False, server_default="1.000000", comment="分组内 Token 调用费用倍率"
        ),
    )


class TokenGroupUser(SQLModelBase, table=True):
    """保存受限 Token 分组与被授权用户的有效关系。"""

    __tablename__ = "token_group_users"
    __table_args__ = (
        Index(
            "uq_token_group_users_group_user_active",
            "group_id",
            "user_id",
            unique=True,
            postgresql_where=text("is_del = false"),
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True, description="分组用户授权关系主键")
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now(), comment="授权创建时间"),
    )
    group_id: int = Field(
        sa_column=Column(
            ForeignKey("token_groups.id", ondelete="RESTRICT"), nullable=False, index=True, comment="受限分组标识"
        )
    )
    user_id: UUID = Field(
        sa_column=Column(
            ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True, comment="获授权用户标识"
        )
    )


class TokenGroupBinding(SQLModelBase, table=True):
    """保存一个 Token 绑定的分组及其由小到大的调度优先级。"""

    __tablename__ = "token_group_bindings"
    __table_args__ = (
        CheckConstraint("priority >= 0", name="ck_token_group_bindings_priority"),
        Index(
            "uq_token_group_bindings_token_group_active",
            "token_id",
            "group_id",
            unique=True,
            postgresql_where=text("is_del = false"),
        ),
        Index(
            "uq_token_group_bindings_token_priority_active",
            "token_id",
            "priority",
            unique=True,
            postgresql_where=text("is_del = false"),
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True, description="Token 分组绑定关系主键")
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now(), comment="绑定创建时间"),
    )
    token_id: UUID = Field(
        sa_column=Column(
            ForeignKey("tokens.id", ondelete="RESTRICT"), nullable=False, index=True, comment="归属 Token 标识"
        )
    )
    group_id: int = Field(
        sa_column=Column(
            ForeignKey("token_groups.id", ondelete="RESTRICT"), nullable=False, index=True, comment="绑定分组标识"
        )
    )
    priority: int = Field(sa_column=Column(Integer, nullable=False, comment="数值越小优先级越高，0 为主分组"))
