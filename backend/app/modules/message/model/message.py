"""消息、消息定向关系与用户已读记录的 ORM 映射。

本模块只保存消息主体、定向对象与已读事实；可见性判定与状态流转由应用服务负责。
"""

import enum
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    func,
    text,
)
from sqlmodel import Field

from app.core.database import SQLModelBase


class MessageType(str, enum.Enum):
    """消息类型的固定枚举，用于前端按类型展示差异化标签。"""

    notice = "notice"
    maintenance = "maintenance"
    update = "update"
    activity = "activity"


def _created_at_column(comment: str) -> Column:
    return Column(DateTime(timezone=True), nullable=False, server_default=func.now(), comment=comment)


def _updated_at_column(comment: str) -> Column:
    return Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(), comment=comment
    )


class Message(SQLModelBase, table=True):
    """站内消息主体，承载内容、类型、可见范围开关与生效/过期时间。"""

    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_active_start", "is_active", "start_at"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True, description="消息主键")
    created_at: datetime | None = Field(default=None, sa_column=_created_at_column("消息创建时间"))
    updated_at: datetime | None = Field(default=None, sa_column=_updated_at_column("消息最近更新时间"))
    title: str = Field(sa_column=Column(String(255), nullable=False, comment="消息标题"))
    content: str = Field(sa_column=Column(Text(), nullable=False, comment="消息正文，markdown 原文"))
    type: MessageType = Field(
        sa_column=Column(Enum(MessageType, name="message_type"), nullable=False, comment="消息类型")
    )
    is_public: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default="false", comment="true 表示对全体用户可见"),
    )
    is_active: bool = Field(
        default=True,
        sa_column=Column(Boolean, nullable=False, server_default="true", comment="false 表示已下架，任何用户不可见"),
    )
    start_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False, comment="消息生效时间"))
    expires_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True, comment="消息过期时间，空表示永不过期"),
    )
    created_by: UUID | None = Field(
        default=None,
        sa_column=Column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, comment="创建消息的管理员"),
    )


class MessageTarget(SQLModelBase, table=True):
    """消息的定向对象关系，两列目标恰好一列非空。"""

    __tablename__ = "message_targets"
    __table_args__ = (
        CheckConstraint(
            "(user_id IS NOT NULL)::int + (token_group_id IS NOT NULL)::int = 1",
            name="ck_message_targets_exactly_one_target",
        ),
        Index("ix_message_targets_message_id", "message_id"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True, description="定向关系主键")
    created_at: datetime | None = Field(default=None, sa_column=_created_at_column("定向关系创建时间"))
    message_id: UUID = Field(
        sa_column=Column(ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, comment="所属消息标识")
    )
    user_id: UUID | None = Field(
        default=None,
        sa_column=Column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, comment="定向用户标识"),
    )
    token_group_id: int | None = Field(
        default=None,
        sa_column=Column(ForeignKey("token_groups.id", ondelete="RESTRICT"), nullable=True, comment="定向 Token 分组"),
    )


class MessageRead(SQLModelBase, table=True):
    """用户对消息的已读事实，用于未读计数与已读标记。"""

    __tablename__ = "message_reads"
    __table_args__ = (
        Index(
            "uq_message_reads_message_user_active",
            "message_id",
            "user_id",
            unique=True,
            postgresql_where=text("is_del = false"),
        ),
        Index("ix_message_reads_user_id", "user_id"),
        Index("ix_message_reads_message_id", "message_id"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True, description="已读记录主键")
    created_at: datetime | None = Field(default=None, sa_column=_created_at_column("已读记录创建时间"))
    message_id: UUID = Field(
        sa_column=Column(ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, comment="消息标识")
    )
    user_id: UUID = Field(
        sa_column=Column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, comment="已读用户标识")
    )
    read_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False, comment="首次标记已读时间"))
