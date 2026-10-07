"""用户账号 SQLModel，定义登录身份及其关联资源。"""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Column, DateTime, Index, String, UniqueConstraint, func
from sqlmodel import Field, Relationship

from app.core.database import SQLModelBase

if TYPE_CHECKING:
    from app.modules.user.model.token import Token
    from app.modules.video.model.video_task import VideoTask
    from app.modules.wallet.model.wallet import Wallet


class User(SQLModelBase, table=True):
    """平台用户持久化模型，保存唯一登录名、密码摘要和账号状态。"""

    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("username", name="users_username_key"), Index("ix_users_username", "username"))

    id: UUID = Field(default_factory=uuid4, primary_key=True, description="应用侧生成的用户主键")
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True), nullable=False, server_default=func.now(), comment="用户首次创建时间"
        ),
    )
    username: str = Field(sa_column=Column(String(128), nullable=False, comment="用户用于登录的唯一用户名"))
    password_hash: str = Field(sa_column=Column(String(256), nullable=False, comment="Argon2 密码摘要，绝不保存明文"))
    email: str | None = Field(
        default=None, sa_column=Column(String(320), nullable=True, comment="注册验证通过后的邮箱")
    )
    is_active: bool = Field(
        default=True, sa_column=Column(Boolean, nullable=False, default=True, comment="禁用后拒绝登录和会话访问")
    )
    is_admin: bool = Field(
        default=False, sa_column=Column(Boolean, nullable=False, default=False, comment="是否具备后台管理员角色")
    )
    tokens: list["Token"] = Relationship(back_populates="user")
    wallet: "Wallet" = Relationship(back_populates="user", sa_relationship_kwargs={"uselist": False})
    video_tasks: list["VideoTask"] = Relationship(back_populates="user")
