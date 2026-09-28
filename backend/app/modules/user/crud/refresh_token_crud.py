"""刷新令牌数据库操作。"""

from datetime import UTC, datetime

from sqlalchemy import select as sqlalchemy_select
from sqlmodel import Session

from app.modules.user.model.refresh_token import RefreshToken


class RefreshTokenCrud:
    """封装刷新令牌的创建与带锁查询。"""

    def __init__(self, session: Session) -> None:
        """绑定外部传入的数据库会话。"""

        self._session = session

    def get_for_update(self, token_hash: str) -> RefreshToken | None:
        """按摘要加行锁查询刷新令牌，防止并发重复轮换。"""

        return self._session.scalar(
            sqlalchemy_select(RefreshToken).where(RefreshToken.token_hash == token_hash).with_for_update()
        )

    def create(self, *, session_id, token_hash: str, expires_at: datetime) -> RefreshToken:
        """创建新的刷新令牌记录。"""

        token = RefreshToken(session_id=session_id, token_hash=token_hash, expires_at=expires_at)
        self._session.add(token)
        return token

    def mark_used(self, token: RefreshToken) -> None:
        """标记刷新令牌已使用，阻止其再次轮换。"""

        token.used_at = datetime.now(UTC)
