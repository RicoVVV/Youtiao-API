"""刷新令牌 SQLModel，保存一次性轮换令牌的安全状态。"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, ForeignKey, String, func
from sqlmodel import Field

from app.core.database import SQLModelBase


class RefreshToken(SQLModelBase, table=True):
    """一次性刷新令牌链，仅保存带 pepper 的不可逆摘要。"""

    __tablename__ = "refresh_tokens"
    id: UUID = Field(default_factory=uuid4, primary_key=True, description="应用侧生成的刷新令牌主键")
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True), nullable=False, server_default=func.now(), comment="刷新令牌创建时间"
        ),
    )
    session_id: UUID = Field(
        sa_column=Column(
            ForeignKey("auth_sessions.id", ondelete="RESTRICT"), nullable=False, index=True, comment="所属会话"
        )
    )
    token_hash: str = Field(sa_column=Column(String(64), nullable=False, unique=True, comment="刷新令牌 pepper 哈希"))
    expires_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, comment="刷新令牌 UTC 失效时间")
    )
    used_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), comment="首次使用时间，非空表示已轮换")
    )
