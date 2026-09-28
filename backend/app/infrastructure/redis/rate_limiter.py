"""认证 Redis 固定窗口限流。"""

import hashlib
from math import ceil

from app.core.config import get_settings
from app.core.errors import AuthenticationRateLimitUnavailableError, RateLimitExceededError
from app.infrastructure.redis.client import auth_rate_limit_circuit_breaker, get_auth_redis_client

_INCREMENT_FIXED_WINDOW = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return {count, redis.call('TTL', KEYS[1])}
"""


def enforce_auth_rate_limit(*, scope: str, client_host: str, limit: int) -> None:
    """按来源地址执行认证固定窗口限流，Redis 不可用时拒绝认证请求。"""

    settings = get_settings()
    key = _rate_limit_key(scope, client_host)
    try:
        count, ttl = auth_rate_limit_circuit_breaker.execute(
            lambda: get_auth_redis_client().eval(
                _INCREMENT_FIXED_WINDOW, 1, key, settings.auth_rate_limit_window_seconds
            )
        )
    except Exception as exc:
        raise AuthenticationRateLimitUnavailableError("认证限流服务暂不可用") from exc
    if int(count) > limit:
        raise RateLimitExceededError(
            max(1, int(ttl) if int(ttl) > 0 else ceil(settings.auth_rate_limit_window_seconds))
        )


def _rate_limit_key(scope: str, client_host: str) -> str:
    subject_digest = hashlib.sha256(client_host.encode()).hexdigest()
    return f"auth:rate-limit:{scope}:{subject_digest}"
