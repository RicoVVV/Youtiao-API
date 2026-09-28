"""认证会话 SQLModel，保存 JWT 会话的可撤销状态。"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, ForeignKey, func
from sqlmodel import Field

from app.core.database import SQLModelBase


class AuthSession(SQLModelBase, table=True):
    """可撤销用户会话，未撤销会话才允许 JWT 继续访问。"""

    __tablename__ = "auth_sessions"
    id: UUID = Field(default_factory=uuid4, primary_key=True, description="应用侧生成的认证会话主键")
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True), nullable=False, server_default=func.now(), comment="认证会话创建时间"
        ),
    )
    user_id: UUID | None = Field(
        default=None,
        sa_column=Column(ForeignKey("users.id", ondelete="RESTRICT"), index=True, comment="用户会话主体"),
    )
    revoked_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), comment="会话撤销时间"))
