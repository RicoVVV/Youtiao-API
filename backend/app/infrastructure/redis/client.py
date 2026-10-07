"""Redis 通用客户端基础设施，负责连接创建、进程缓存与认证库客户端获取。

本模块不承载限流阈值、锁键或降级策略；调用方必须根据具体业务决定 Redis 故障的处理方式。
"""

from functools import lru_cache
from threading import Lock
from time import monotonic

from redis import Redis

from app.core.config import get_settings


class RedisCircuitOpenError(Exception):
    pass


class RedisCircuitBreaker:
    def __init__(self) -> None:
        self._lock = Lock()
        self._open_until = 0.0

    def execute(self, operation):
        with self._lock:
            if monotonic() < self._open_until:
                raise RedisCircuitOpenError("Redis 熔断中")
        try:
            result = operation()
        except Exception:
            with self._lock:
                self._open_until = monotonic() + get_settings().auth_redis_circuit_breaker_seconds
            raise
        with self._lock:
            self._open_until = 0.0
        return result

    def reset(self) -> None:
        with self._lock:
            self._open_until = 0.0


auth_rate_limit_circuit_breaker = RedisCircuitBreaker()
auth_session_cache_circuit_breaker = RedisCircuitBreaker()
routing_snapshot_circuit_breaker = RedisCircuitBreaker()


@lru_cache
def get_redis_client() -> Redis:
    """返回进程复用 Redis 客户端，连接错误由具体调用按可用性策略处理。"""

    return Redis.from_url(
        get_settings().auth_redis_url, decode_responses=True, socket_connect_timeout=1, socket_timeout=1
    )


@lru_cache
def get_auth_redis_client() -> Redis:
    """返回认证专用 Redis 客户端，调用方必须在故障时回源认证数据库。"""

    return Redis.from_url(
        get_settings().auth_redis_url, decode_responses=True, socket_connect_timeout=1, socket_timeout=1
    )
