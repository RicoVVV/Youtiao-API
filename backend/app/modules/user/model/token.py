"""长期 Token SQLModel，保存凭证归属、明文及可用状态。"""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, func
from sqlmodel import Field, Relationship

from app.core.database import SQLModelBase

if TYPE_CHECKING:
    from app.modules.user.model.user import User


class Token(SQLModelBase, table=True):
    """长期 API Token 持久化模型，按产品要求明文保存以支持再次复制。"""

    __tablename__ = "tokens"
    id: UUID = Field(default_factory=uuid4, primary_key=True, description="应用侧生成的 Token 主键")
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now(), comment="Token 创建时间"),
    )
    user_id: UUID = Field(
        sa_column=Column(
            ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True, comment="Token 归属用户"
        )
    )
    token: str = Field(
        sa_column=Column(String(512), nullable=False, unique=True, comment="完整明文 Token，供用户后续查看和复制")
    )
    label: str | None = Field(default=None, sa_column=Column(String(128), comment="用户可读的 Token 用途标签"))
    is_active: bool = Field(
        default=True,
        sa_column=Column(
            Boolean, nullable=False, server_default="true", comment="Token 是否允许鉴权，false 表示暂时禁用"
        ),
    )
    last_used_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), comment="最近成功 API 调用时间")
    )
    user: "User" = Relationship(back_populates="tokens")
