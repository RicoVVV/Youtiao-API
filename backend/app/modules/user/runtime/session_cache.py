"""用户认证 Redis 会话缓存，缓存异常时由调用方回源数据库。"""

import json
from dataclasses import asdict, dataclass
from datetime import datetime

from app.core.config import get_settings
from app.infrastructure.redis.client import auth_session_cache_circuit_breaker, get_auth_redis_client


@dataclass(frozen=True, slots=True)
class AuthSessionCache:
    """Redis 中的认证会话快照，只保存 JWT 实时校验需要的最小用户状态。"""

    session_id: str
    user_id: str
    username: str
    is_active: bool
    is_admin: bool
    created_at: datetime


def read_auth_session_cache(session_id: str) -> AuthSessionCache | None:
    """读取认证会话缓存，Redis 异常由调用方捕获并回源数据库。"""

    raw_value = auth_session_cache_circuit_breaker.execute(lambda: get_auth_redis_client().get(_cache_key(session_id)))
    if raw_value is None:
        return None
    payload = json.loads(raw_value)
    return AuthSessionCache(
        session_id=payload["session_id"],
        user_id=payload["user_id"],
        username=payload["username"],
        is_active=payload["is_active"],
        is_admin=payload["is_admin"],
        created_at=datetime.fromisoformat(payload["created_at"]),
    )


def write_auth_session_cache(snapshot: AuthSessionCache) -> None:
    """写入认证会话缓存，TTL 不得长于 access JWT 的最长有效期。"""

    payload = asdict(snapshot)
    payload["created_at"] = snapshot.created_at.isoformat()
    auth_session_cache_circuit_breaker.execute(
        lambda: get_auth_redis_client().setex(
            _cache_key(snapshot.session_id), get_settings().access_token_minutes * 60, json.dumps(payload)
        )
    )


def delete_auth_session_cache(session_id: str) -> None:
    """删除已撤销会话缓存，提交后的后续请求将回源数据库校验。"""

    auth_session_cache_circuit_breaker.execute(lambda: get_auth_redis_client().delete(_cache_key(session_id)))


def _cache_key(session_id: str) -> str:
    """生成认证专用缓存键，避免与限流和任务协调键冲突。"""

    return f"auth:session:{session_id}"
