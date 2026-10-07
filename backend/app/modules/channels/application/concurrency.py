"""解析任务并发策略，并提供原子租约占用和终态释放服务。"""

from datetime import UTC, datetime
from uuid import UUID

from sqlmodel import Session

from app.modules.channels.crud.concurrency import ConcurrencyCrud


class ConcurrencyLimitExceeded(ValueError):
    """表示用户至少一个命中维度已达到管理员设定的并发上限。"""


def reserve_task_concurrency(session: Session, *, task_id: UUID, user_id: UUID, model_id: UUID) -> None:
    """原子校验命中上限，并为视频任务写入并发租约。

    锁定用户行以串行化同一用户的创建请求；任一维度无余量时抛出
    ConcurrencyLimitExceeded。调用方必须将本服务与任务、账务状态变更置于同一事务。
    """

    crud = ConcurrencyCrud(session)
    existing = crud.get_lease_by_task_id(task_id=task_id)
    if existing is not None:
        return
    crud.lock_user(user_id=user_id)
    model, override = crud.get_model_and_override_for_update(user_id=user_id, model_id=model_id)
    if model is None:
        raise ValueError("模型不存在或已被删除")
    limit = override.concurrency_limit if override is not None and override.active else model.default_concurrency_limit
    if limit is None:
        return
    if limit == 0 or crud.count_active_leases(user_id=user_id, model_id=model_id) >= limit:
        raise ConcurrencyLimitExceeded("当前并发任务数已达上限")
    crud.create_lease(task_id=task_id, user_id=user_id, model_id=model_id)


def release_task_concurrency(session: Session, *, task_id: UUID) -> bool:
    """幂等标记指定任务的并发租约已释放。

    返回值表示是否首次释放；租约不存在或已释放时返回 False。
    """

    crud = ConcurrencyCrud(session)
    lease = crud.get_lease_by_task_id_for_update(task_id=task_id)
    if lease is None or lease.released_at is not None:
        return False
    crud.release_lease(lease=lease, released_at=datetime.now(UTC))
    return True
