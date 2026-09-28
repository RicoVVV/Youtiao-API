"""JWT 与刷新令牌安全原语，不访问 HTTP 请求或数据库。"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt

from app.core.config import get_settings


def hash_refresh_token(raw_token: str) -> str:
    """计算刷新令牌的带 pepper 检索摘要。"""

    return hashlib.sha256(get_settings().refresh_token_pepper.encode() + raw_token.encode()).hexdigest()


def generate_refresh_token() -> tuple[str, str]:
    """生成仅在响应中出现一次的刷新令牌及其存储摘要。"""

    raw_token = secrets.token_urlsafe(48)
    return raw_token, hash_refresh_token(raw_token)


def create_access_token(*, subject_id: UUID, roles: list[str], session_id: UUID) -> str:
    """签发固定短期访问 JWT，角色集合只能由服务端账号状态生成。"""

    settings = get_settings()
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": str(subject_id),
            "roles": roles,
            "sid": str(session_id),
            "jti": str(uuid4()),
            "iat": now,
            "exp": now + timedelta(minutes=settings.access_token_minutes),
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
        },
        settings.jwt_signing_key,
        algorithm="HS256",
    )


def decode_access_token(access_token: str) -> dict:
    """严格验证 JWT 的签名、发行者、受众和固定算法。"""

    settings = get_settings()
    return jwt.decode(
        access_token,
        settings.jwt_signing_key,
        algorithms=["HS256"],
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
    )
