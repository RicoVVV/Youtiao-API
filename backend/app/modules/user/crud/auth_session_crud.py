"""认证会话数据库操作。"""

from datetime import UTC, datetime
from uuid import UUID

from sqlmodel import Session

from app.modules.user.model.auth_session import AuthSession


class AuthSessionCrud:
    """封装可撤销认证会话的查询、创建和撤销操作。"""

    def __init__(self, session: Session) -> None:
        """绑定外部传入的数据库会话。"""

        self._session = session

    def get(self, session_id: UUID) -> AuthSession | None:
        """按会话标识查询认证会话。"""

        return self._session.get(AuthSession, session_id)

    def create(self, user_id: UUID) -> AuthSession:
        """创建认证会话并刷新主键。"""

        auth_session = AuthSession(user_id=user_id)
        self._session.add(auth_session)
        self._session.flush()
        return auth_session

    def revoke(self, auth_session: AuthSession) -> None:
        """撤销会话，重复调用保持幂等。"""

        if auth_session.revoked_at is None:
            auth_session.revoked_at = datetime.now(UTC)

    def revoke_by_user_and_session(self, user_id: UUID, session_id: UUID) -> AuthSession | None:
        """按用户与会话联合条件撤销当前设备会话，避免误撤销其他设备。"""

        auth_session = self._session.get(AuthSession, session_id)
        if auth_session is None or auth_session.user_id != user_id:
            return None
        self.revoke(auth_session)
        return auth_session
