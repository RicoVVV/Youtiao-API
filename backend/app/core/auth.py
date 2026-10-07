"""统一暴露网页端 JWT 与对外长期 Token 的路由鉴权依赖。"""

import logging
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session

from app.core.config import get_settings
from app.core.database import get_db, get_session_factory
from app.infrastructure.redis.rate_limiter import enforce_auth_rate_limit
from app.modules.user.application.auth.contracts import AuthenticatedUser
from app.modules.user.application.token.contracts import RuntimeTokenGroups
from app.modules.user.application.token.services import TokenApplicationService
from app.modules.user.crud.auth_session_crud import AuthSessionCrud
from app.modules.user.crud.token_crud import TokenCrud
from app.modules.user.crud.user_crud import UserCrud
from app.modules.user.runtime.session_cache import AuthSessionCache, read_auth_session_cache, write_auth_session_cache
from app.modules.user.security.jwt import decode_access_token

logger = logging.getLogger(__name__)
bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True, slots=True)
class TokenAuthorizationContext:
    """对外长期 Token 鉴权后提供的用户与全部有效分组上下文。"""

    user_id: UUID
    token_id: UUID
    token_display_name: str | None
    token_groups: RuntimeTokenGroups


def get_user_id(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: Annotated[Session, Depends(get_db)],
) -> UUID:
    """校验短期 JWT Bearer、用户和会话状态，并返回当前用户标识。

    参数：request 用于保存本次已验证的会话标识，credentials 为 Bearer 凭据，session 为数据库会话。
    返回值：当前启用用户的 UUID。
    异常：JWT 缺失、无效、会话撤销、会话归属不符或用户停用时抛出 401。
    """

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="缺少有效访问令牌")
    try:
        claims = decode_access_token(credentials.credentials)
        if "user" not in claims.get("roles", []):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="用户权限不足")
        user, session_id = _require_authenticated_user(claims, session)
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="访问令牌无效") from exc
    request.state.user_id = user.id
    request.state.session_id = session_id
    return user.id


def get_admin_user_id(
    user_id: Annotated[UUID, Depends(get_user_id)], session: Annotated[Session, Depends(get_db)]
) -> UUID:
    """实时复核当前已认证用户的管理员角色并返回其标识。

    参数：user_id 为已完成 JWT、会话与用户状态校验的标识，session 为当前请求数据库会话。
    返回值：当前仍拥有管理员角色的用户 UUID。
    异常：用户不存在或管理员角色已取消时抛出 HTTP 403。
    """

    user = UserCrud(session).get_by_id(user_id)
    if user is None or not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="管理员权限不足")
    return user_id


def require_token(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: Annotated[Session, Depends(get_db)],
) -> UUID:
    """校验对外 API 的 `sk-...` 长期 Bearer Token。

    参数：credentials 为 Bearer 凭据，session 为数据库会话。
    返回值：有效长期 Token 所属用户的 UUID，不向业务 API 泄露持久化模型。
    异常：凭据缺失、格式不符或已失效时抛出 401。
    """

    if credentials is None or credentials.scheme.lower() != "bearer":
        _enforce_invalid_api_key_rate_limit(request)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="缺少 Bearer Token")
    raw_token = credentials.credentials
    if not raw_token.startswith("sk-") or len(raw_token) > 512:
        _enforce_invalid_api_key_rate_limit(request)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效 Token")
    token = TokenCrud(session).authenticate(raw_token)
    if token is None:
        _enforce_invalid_api_key_rate_limit(request)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效 Token")
    return token.user_id


def require_token_group(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> TokenAuthorizationContext:
    """校验长期 Token 并解析实时可用的全部绑定分组。

    参数：credentials 为 Bearer 凭据。
    返回值：Token 所属用户及其按优先级排序的全部有效分组上下文。
    异常：Token 无效时返回 401，全部绑定分组均无效时返回 403。
    """

    if credentials is None or credentials.scheme.lower() != "bearer":
        _enforce_invalid_api_key_rate_limit(request)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="缺少 Bearer Token")
    raw_token = credentials.credentials
    if not raw_token.startswith("sk-") or len(raw_token) > 512:
        _enforce_invalid_api_key_rate_limit(request)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效 Token")
    with get_session_factory()() as session:
        token = TokenCrud(session).authenticate(raw_token)
        if token is None:
            _enforce_invalid_api_key_rate_limit(request)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效 Token")
        try:
            token_groups = TokenApplicationService(session).get_runtime_groups(token_id=token.id, user_id=token.user_id)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前分组不可用") from exc
        return TokenAuthorizationContext(
            user_id=token.user_id,
            token_id=token.id,
            token_display_name=getattr(token, "label", None),
            token_groups=token_groups,
        )


def enforce_login_rate_limit(client_host: str) -> None:
    enforce_auth_rate_limit(scope="login", client_host=client_host, limit=get_settings().auth_login_rate_limit)


def enforce_refresh_rate_limit(client_host: str) -> None:
    enforce_auth_rate_limit(scope="refresh", client_host=client_host, limit=get_settings().auth_refresh_rate_limit)


def _enforce_invalid_api_key_rate_limit(request: Request) -> None:
    client_host = request.client.host if request.client else "unknown"
    enforce_auth_rate_limit(
        scope="invalid-api-key", client_host=client_host, limit=get_settings().auth_invalid_api_key_rate_limit
    )


def _require_authenticated_user(claims: dict, session: Session) -> tuple[AuthenticatedUser, UUID]:
    """通过缓存或数据库复核 JWT 主体、会话归属和撤销状态。"""

    try:
        subject_id = UUID(claims["sub"])
        session_id = UUID(claims["sid"])
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="访问令牌无效") from exc
    cached = _read_cached_user(session_id)
    if cached is not None:
        if cached.id != subject_id or not cached.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="会话已失效")
        return cached, session_id
    user = UserCrud(session).get_by_id(subject_id)
    auth_session = AuthSessionCrud(session).get(session_id)
    if (
        user is None
        or not user.is_active
        or auth_session is None
        or auth_session.user_id != user.id
        or auth_session.revoked_at
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="会话已失效")
    authenticated = AuthenticatedUser(
        id=user.id,
        username=user.username,
        is_active=user.is_active,
        is_admin=user.is_admin,
        created_at=user.created_at,
    )
    _write_cached_user(session_id, authenticated)
    return authenticated, session_id


def _read_cached_user(session_id: UUID) -> AuthenticatedUser | None:
    """读取认证缓存；缓存异常或非法快照时回源数据库。"""

    try:
        cached = read_auth_session_cache(str(session_id))
        if cached is None or cached.session_id != str(session_id):
            return None
        return AuthenticatedUser(
            id=UUID(cached.user_id),
            username=cached.username,
            is_active=cached.is_active,
            is_admin=cached.is_admin,
            created_at=cached.created_at,
        )
    except Exception:
        logger.warning("认证会话缓存读取失败，回源 PostgreSQL session_id=%s", session_id, exc_info=True)
        return None


def _write_cached_user(session_id: UUID, user: AuthenticatedUser) -> None:
    """尽力回填数据库已校验的会话快照，不影响认证成功结果。"""

    try:
        write_auth_session_cache(
            AuthSessionCache(
                session_id=str(session_id),
                user_id=str(user.id),
                username=user.username,
                is_active=user.is_active,
                is_admin=user.is_admin,
                created_at=user.created_at,
            )
        )
    except Exception:
        logger.warning("认证会话缓存回填失败 session_id=%s", session_id, exc_info=True)
