"""站内通知、通知定向关系与用户关闭记录的 ORM 映射。

通知全局同一时刻只有一条生效中，由部分唯一索引在数据库层保证；可见性判定与状态流转由应用服务负责。
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    text,
)
from sqlmodel import Field

from app.core.database import SQLModelBase
from app.modules.message.model.message import _created_at_column, _updated_at_column


class Notification(SQLModelBase, table=True):
    """站内通知主体，用户进入网站时以弹窗展示，全局最多一条生效中。"""

    __tablename__ = "notifications"
    __table_args__ = (
        Index(
            "uq_notifications_active",
            "is_active",
            unique=True,
            postgresql_where=text("is_active = true AND is_del = false"),
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True, description="通知主键")
    created_at: datetime | None = Field(default=None, sa_column=_created_at_column("通知创建时间"))
    updated_at: datetime | None = Field(default=None, sa_column=_updated_at_column("通知最近更新时间"))
    title: str = Field(sa_column=Column(String(255), nullable=False, comment="通知标题"))
    content: str = Field(sa_column=Column(Text(), nullable=False, comment="通知正文，markdown 原文"))
    is_public: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default="false", comment="true 表示对全体用户可见"),
    )
    is_active: bool = Field(
        default=True,
        sa_column=Column(Boolean, nullable=False, server_default="true", comment="true 表示全局唯一生效中"),
    )
    start_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False, comment="通知生效时间"))
    expires_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True, comment="通知过期时间，空表示永不过期"),
    )
    created_by: UUID | None = Field(
        default=None,
        sa_column=Column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, comment="创建通知的管理员"),
    )


class NotificationTarget(SQLModelBase, table=True):
    """通知的定向对象关系，两列目标恰好一列非空。"""

    __tablename__ = "notification_targets"
    __table_args__ = (
        CheckConstraint(
            "(user_id IS NOT NULL)::int + (token_group_id IS NOT NULL)::int = 1",
            name="ck_notification_targets_exactly_one_target",
        ),
        Index("ix_notification_targets_notification_id", "notification_id"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True, description="定向关系主键")
    created_at: datetime | None = Field(default=None, sa_column=_created_at_column("定向关系创建时间"))
    notification_id: UUID = Field(
        sa_column=Column(ForeignKey("notifications.id", ondelete="CASCADE"), nullable=False, comment="所属通知标识")
    )
    user_id: UUID | None = Field(
        default=None,
        sa_column=Column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, comment="定向用户标识"),
    )
    token_group_id: int | None = Field(
        default=None,
        sa_column=Column(ForeignKey("token_groups.id", ondelete="RESTRICT"), nullable=True, comment="定向 Token 分组"),
    )


class NotificationDismissal(SQLModelBase, table=True):
    """用户关闭通知的事实，用于“关闭后不再弹”。"""

    __tablename__ = "notification_dismissals"
    __table_args__ = (
        Index(
            "uq_notification_dismissals_notification_user_active",
            "notification_id",
            "user_id",
            unique=True,
            postgresql_where=text("is_del = false"),
        ),
        Index("ix_notification_dismissals_user_id", "user_id"),
        Index("ix_notification_dismissals_notification_id", "notification_id"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True, description="关闭记录主键")
    created_at: datetime | None = Field(default=None, sa_column=_created_at_column("关闭记录创建时间"))
    notification_id: UUID = Field(
        sa_column=Column(ForeignKey("notifications.id", ondelete="CASCADE"), nullable=False, comment="通知标识")
    )
    user_id: UUID = Field(
        sa_column=Column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, comment="关闭用户标识")
    )
    dismissed_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False, comment="关闭时间"))
