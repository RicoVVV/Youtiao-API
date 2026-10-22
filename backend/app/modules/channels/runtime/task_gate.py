"""后台任务的节流闸门，避免 30 秒调度循环放大探测与采样频率。"""

import logging

from app.infrastructure.redis.client import get_redis_client

logger = logging.getLogger(__name__)


def acquire_window(scope: str, seconds: int) -> bool:
    """在 Redis 中抢占一个固定窗口；成功表示本轮允许执行。

    Redis 不可用时返回 ``True``，由调用方继续执行并依赖各自的状态写入失败降级。
    """

    try:
        return bool(get_redis_client().set(f"routing:schedule:{scope}", "1", nx=True, ex=seconds))
    except Exception:
        logger.warning("后台任务节流闸门不可用，按允许执行处理 scope=%s", scope, exc_info=True)
        return True
