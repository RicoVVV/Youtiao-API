"""注册邮箱验证码的 Redis 存储，键中邮箱使用 SHA-256 摘要以避免明文落库。"""

import hashlib
import hmac
import secrets

from redis.exceptions import RedisError

from app.core.errors import AuthenticationProviderUnavailableError, RateLimitExceededError, ValidationError
from app.infrastructure.redis.client import get_auth_redis_client

CODE_TTL_SECONDS = 600  # 验证码有效期 10 分钟
_COOLDOWN_TTL = 60  # 同邮箱冷却 60 秒
_MAX_ATTEMPTS = 5  # 最大错误次数


def _digest(email: str) -> str:
    return hashlib.sha256(email.lower().encode()).hexdigest()


def _code_key(digest: str) -> str:
    return f"auth:email-code:{digest}"


def _attempts_key(digest: str) -> str:
    return f"auth:email-code-attempts:{digest}"


def _cooldown_key(digest: str) -> str:
    return f"auth:email-code-cooldown:{digest}"


def _code_hash(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def generate_code() -> str:
    """生成 6 位数字验证码。"""
    return f"{secrets.randbelow(1000000):06d}"


def check_cooldown(email: str) -> None:
    """同邮箱 60 秒冷却检查，冷却中时抛出 RateLimitExceededError。"""
    try:
        ttl = get_auth_redis_client().ttl(_cooldown_key(_digest(email)))
    except RedisError as exc:
        raise AuthenticationProviderUnavailableError("验证码服务暂不可用") from exc
    if int(ttl) > 0:
        raise RateLimitExceededError(int(ttl))


def save_code(email: str, code: str) -> None:
    """保存验证码摘要和冷却标记，覆盖旧验证码。"""
    try:
        r = get_auth_redis_client()
        digest = _digest(email)
        r.set(_code_key(digest), _code_hash(code), ex=CODE_TTL_SECONDS)
        r.set(_cooldown_key(digest), "1", ex=_COOLDOWN_TTL)
        r.delete(_attempts_key(digest))
    except RedisError as exc:
        raise AuthenticationProviderUnavailableError("验证码服务暂不可用") from exc


def delete_code(email: str) -> None:
    """验证成功或失败超限后清除验证码及计数。"""
    try:
        digest = _digest(email)
        get_auth_redis_client().delete(_code_key(digest), _attempts_key(digest))
    except RedisError:
        pass  # 清除失败不影响业务，验证码会随 TTL 自然过期


def release_code(email: str) -> None:
    """发信失败后撤销验证码、计数与冷却标记，允许用户立即重试。"""
    try:
        digest = _digest(email)
        get_auth_redis_client().delete(_code_key(digest), _attempts_key(digest), _cooldown_key(digest))
    except RedisError:
        pass  # 清除失败不影响业务，键会随 TTL 自然过期


def consume_code(email: str, code: str) -> None:
    """校验验证码，成功后删除；错误次数超限后删除并抛出 ValidationError。"""
    try:
        r = get_auth_redis_client()
        digest = _digest(email)
        stored = r.get(_code_key(digest))
        if stored is None:
            raise ValidationError("验证码已过期或不存在，请重新获取")
        if not hmac.compare_digest(str(stored), _code_hash(code)):
            attempts = r.incr(_attempts_key(digest))
            ttl = r.ttl(_code_key(digest))
            if int(ttl) > 0:
                r.expire(_attempts_key(digest), int(ttl))
            if int(attempts) >= _MAX_ATTEMPTS:
                delete_code(email)
                raise ValidationError("验证码错误次数过多，请重新获取")
            raise ValidationError("验证码错误")
        delete_code(email)
    except ValidationError:
        raise
    except RedisError as exc:
        raise AuthenticationProviderUnavailableError("验证码服务暂不可用") from exc
