"""认证应用服务，封装注册、会话、令牌、限流及认证缓存的完整业务用例。"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlmodel import Session

from app.core.config import get_settings
from app.core.errors import AuthenticationError, ConflictError, NotFoundError
from app.modules.user.application.auth.contracts import UserProfileData
from app.modules.user.crud.auth_session_crud import AuthSessionCrud
from app.modules.user.crud.refresh_token_crud import RefreshTokenCrud
from app.modules.user.crud.user_crud import UserCrud
from app.modules.user.model.auth_session import AuthSession
from app.modules.user.model.user import User
from app.modules.user.runtime.session_cache import AuthSessionCache, delete_auth_session_cache, write_auth_session_cache
from app.modules.user.security.jwt import create_access_token, generate_refresh_token, hash_refresh_token
from app.modules.user.security.password import hash_password, verify_password
from app.modules.wallet.crud.wallet_crud import WalletCrud

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RegisteredUser:
    """注册用例返回的新用户，不在注册阶段签发 API Key。"""

    user: User


@dataclass(frozen=True, slots=True)
class IssuedAuthTokens:
    """登录或刷新成功后返回的令牌与认证缓存预热快照。"""

    access_token: str
    refresh_token: str
    cache_snapshot: AuthSessionCache


class RefreshSessionRevokedError(AuthenticationError):
    """刷新令牌重放或主体禁用导致会话撤销后抛出的可提交认证异常。"""

    def __init__(self, session_id: UUID) -> None:
        """记录已在当前事务中撤销的会话标识，供路由提交后失效缓存。"""

        super().__init__("刷新令牌重放或主体已禁用")
        self.session_id = session_id


class UsernameAlreadyExistsError(ConflictError):
    """注册用户名已存在时抛出。"""


class SetupAlreadyCompletedError(ConflictError):
    """首次管理员已创建而安装入口关闭时抛出。"""


class InvalidCredentialsError(AuthenticationError):
    """用户名、密码或账户状态不满足登录条件时抛出。"""


class InvalidRefreshTokenError(AuthenticationError):
    """刷新令牌缺失、过期或无效时抛出。"""


class AuthSessionNotFoundError(AuthenticationError):
    """当前用户的认证会话不存在时抛出。"""


class AuthApplicationService:
    """处理注册、密码认证和可撤销会话的事务型应用用例。"""

    def __init__(self, session: Session) -> None:
        """接收请求级会话，并在每个认证用例内管理提交、回滚和缓存副作用。"""

        self._session = session
        self._users = UserCrud(session)
        self._auth_sessions = AuthSessionCrud(session)
        self._refresh_tokens = RefreshTokenCrud(session)

    def register_user(self, *, username: str, password: str) -> RegisteredUser:
        """注册用户并在同一事务创建钱包，不自动签发 API Key。

        参数：username 为唯一用户名，password 为符合长度要求的登录密码。
        返回值：创建后的用户。
        异常：用户名重复时抛出 UsernameAlreadyExistsError；其他写入异常将回滚。
        """

        try:
            if self._users.get_by_username(username) is not None:
                raise UsernameAlreadyExistsError("用户名已存在")
            user = self._users.create(username=username, password_hash=hash_password(password))
            # 用户主键已刷新，才能在同一事务内建立钱包归属关系。
            WalletCrud(self._session).create_wallet(user.id)
            self._session.commit()
            return RegisteredUser(user=user)
        except Exception:
            self._session.rollback()
            raise

    def is_setup_required(self) -> bool:
        """返回系统是否尚未创建管理员，供前端决定展示初始化还是登录界面。"""

        return not self._users.has_admin()

    def setup_initial_admin(self, *, username: str, password: str) -> RegisteredUser:
        """在无管理员的首次安装阶段创建唯一管理员及其初始钱包。

        参数：username 和 password 为首次管理员登录凭据。
        返回值：创建后的管理员用户。
        异常：已有管理员时抛出 SetupAlreadyCompletedError；用户名重复时抛出 UsernameAlreadyExistsError。
        副作用：在当前 PostgreSQL 事务中串行化初始化、创建管理员和钱包并提交。
        """

        try:
            self._users.acquire_initial_admin_lock()
            if self._users.has_admin():
                raise SetupAlreadyCompletedError("系统已完成管理员初始化")
            if self._users.get_by_username(username) is not None:
                raise UsernameAlreadyExistsError("用户名已存在")
            user = self._users.create(username=username, password_hash=hash_password(password), is_admin=True)
            WalletCrud(self._session).create_wallet(user.id)
            self._session.commit()
            return RegisteredUser(user=user)
        except Exception:
            self._session.rollback()
            raise

    def get_user_profile(self, user_id: UUID) -> UserProfileData:
        """查询已认证用户的基础资料安全投影。

        参数：user_id 为鉴权依赖已校验的当前用户标识。
        返回值：不含密码、会话和 ORM 状态的用户资料。
        异常：用户不存在时抛出 ValueError。
        """

        user = self._users.get_by_id(user_id)
        if user is None:
            raise NotFoundError("已认证用户不存在")
        return UserProfileData(
            id=user.id,
            username=user.username,
            is_active=user.is_active,
            is_admin=user.is_admin,
            created_at=user.created_at,
        )

    def login(self, *, username: str, password: str, client_host: str) -> IssuedAuthTokens:
        """创建认证会话和刷新令牌，并在提交后预热认证缓存。"""
        try:
            user = self._users.get_by_username(username)
            if user is None or not user.is_active or not verify_password(password, user.password_hash):
                raise InvalidCredentialsError("用户名或密码错误")
            auth_session = self._auth_sessions.create(user.id)
            raw_refresh, refresh_hash = generate_refresh_token()
            self._refresh_tokens.create(
                session_id=auth_session.id,
                token_hash=refresh_hash,
                expires_at=datetime.now(UTC) + timedelta(days=get_settings().refresh_token_days),
            )
            tokens = IssuedAuthTokens(
                access_token=create_access_token(
                    subject_id=user.id, roles=_roles_for_user(user), session_id=auth_session.id
                ),
                refresh_token=raw_refresh,
                cache_snapshot=_auth_session_cache_snapshot(user, auth_session),
            )
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
        self._warm_auth_session_cache(tokens.cache_snapshot)
        return tokens

    def refresh(self, *, raw_refresh: str | None, client_host: str) -> IssuedAuthTokens:
        """原子轮换令牌，重放或禁用时撤销会话并清理缓存。"""
        try:
            if raw_refresh is None:
                raise InvalidRefreshTokenError("缺少刷新令牌")
            token = self._refresh_tokens.get_for_update(hash_refresh_token(raw_refresh))
            if token is None or token.expires_at <= datetime.now(UTC):
                raise InvalidRefreshTokenError("刷新令牌无效")
            auth_session = self._auth_sessions.get(token.session_id)
            if token.used_at or auth_session is None or auth_session.revoked_at:
                if auth_session:
                    self._auth_sessions.revoke(auth_session)
                    self._session.commit()
                    self._delete_auth_session_cache(auth_session.id)
                    raise RefreshSessionRevokedError(auth_session.id)
                raise InvalidRefreshTokenError("刷新令牌无效")
            subject = self._users.get_by_id(auth_session.user_id)
            # 刷新令牌可长期保存，因此每次轮换都重新检查主体状态，避免禁用账户继续续期。
            if subject is None or not subject.is_active:
                self._auth_sessions.revoke(auth_session)
                self._session.commit()
                self._delete_auth_session_cache(auth_session.id)
                raise RefreshSessionRevokedError(auth_session.id)
            self._refresh_tokens.mark_used(token)
            raw_new, hash_new = generate_refresh_token()
            self._refresh_tokens.create(
                session_id=token.session_id,
                token_hash=hash_new,
                expires_at=datetime.now(UTC) + timedelta(days=get_settings().refresh_token_days),
            )
            tokens = IssuedAuthTokens(
                access_token=create_access_token(
                    subject_id=subject.id, roles=_roles_for_user(subject), session_id=auth_session.id
                ),
                refresh_token=raw_new,
                cache_snapshot=_auth_session_cache_snapshot(subject, auth_session),
            )
            self._session.commit()
        except RefreshSessionRevokedError:
            raise
        except Exception:
            self._session.rollback()
            raise
        self._warm_auth_session_cache(tokens.cache_snapshot)
        return tokens

    def logout(self, *, user_id: UUID, auth_session_id: UUID) -> None:
        """撤销用户当前认证会话，提交后尽力清理缓存，不影响其他设备会话。"""

        try:
            auth_session = self._auth_sessions.revoke_by_user_and_session(user_id, auth_session_id)
            if auth_session is None:
                raise AuthSessionNotFoundError("会话已失效")
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
        self._delete_auth_session_cache(auth_session.id)

    @staticmethod
    def _warm_auth_session_cache(snapshot: AuthSessionCache) -> None:
        """在认证事务提交后尽力预热会话缓存，失败时由后续请求回源数据库。"""

        try:
            write_auth_session_cache(snapshot)
        except Exception:
            logger.warning("认证会话缓存预热失败 session_id=%s", snapshot.session_id, exc_info=True)

    @staticmethod
    def _delete_auth_session_cache(session_id: UUID) -> None:
        """在会话撤销提交后尽力失效缓存，失败时由认证校验回源数据库。"""

        try:
            delete_auth_session_cache(str(session_id))
        except Exception:
            logger.error("认证会话缓存删除失败 session_id=%s", session_id, exc_info=True)


def _roles_for_user(user: User) -> list[str]:
    """根据数据库实时角色构建令牌声明，禁止由客户端选择管理员资格。"""

    return ["user", "admin"] if user.is_admin else ["user"]


def _auth_session_cache_snapshot(user: User, auth_session: AuthSession) -> AuthSessionCache:
    """构造提交后写入 Redis 的最小会话认证快照，不携带密码或刷新令牌信息。"""

    return AuthSessionCache(
        session_id=str(auth_session.id),
        user_id=str(user.id),
        username=user.username,
        is_active=user.is_active,
        is_admin=user.is_admin,
        created_at=user.created_at,
    )
