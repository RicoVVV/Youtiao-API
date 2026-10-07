"""健康探针路由，提供应用进程存活状态。"""

from fastapi import APIRouter

router = APIRouter(prefix="/health", tags=["健康检查"])


@router.get("", summary="健康检查")
def liveness() -> dict[str, str]:
    """返回进程存活状态。

    返回：始终返回 HTTP 200 和进程状态。
    副作用：不访问外部依赖，避免短暂故障导致编排器重启可用进程。
    """

    return {"status": "ok"}
