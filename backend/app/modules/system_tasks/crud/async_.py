from datetime import UTC, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import case, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.system_tasks.model.system_task import SystemTask, SystemTaskStatus

ACTIVE_KEY_RETAINING_TASK_TYPES = (
    "usage_statistics_rebuild",
    "group_monitor_aggregate",
    "server_metric_collect",
)
"""完成后保留活动键的任务类型。

这类任务的活动键标识"已完成的一次周期性作业"，保留后同一活动键不会再被入队，
调度循环因此不会每隔一个周期就重复执行同一个作业。
"""


class AsyncSystemTaskCrud:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_if_absent(self, *, task_type: str, active_key: str | None = None) -> SystemTask | None:
        statement = (
            insert(SystemTask)
            .values(task_type=task_type, active_key=active_key or task_type, status=SystemTaskStatus.pending)
            .on_conflict_do_nothing(index_elements=["active_key"])
            .returning(SystemTask)
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def create_usage_statistics_if_absent(self) -> SystemTask | None:
        stat_date = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
        return await self.create_if_absent(
            task_type="usage_statistics_rebuild", active_key=f"usage_statistics_rebuild:{stat_date}"
        )

    async def claim_next(self, *, runner_id: str, lease_seconds: int) -> SystemTask | None:
        now = datetime.now(UTC)
        candidate = (
            select(SystemTask.id)
            .where(
                or_(
                    SystemTask.status == SystemTaskStatus.pending,
                    (SystemTask.status == SystemTaskStatus.running) & (SystemTask.lease_expires_at <= now),
                )
            )
            .order_by(SystemTask.created_at, SystemTask.id)
            .limit(1)
            .with_for_update(skip_locked=True)
            .cte("system_task_candidate")
        )
        statement = (
            update(SystemTask)
            .where(SystemTask.id == candidate.c.id)
            .values(
                status=SystemTaskStatus.running,
                runner_id=runner_id,
                started_at=now,
                lease_expires_at=now + timedelta(seconds=lease_seconds),
                error=None,
            )
            .returning(SystemTask)
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def get_task_type(self, *, task_id: UUID) -> str:
        return (await self._session.scalar(select(SystemTask.task_type).where(SystemTask.id == task_id))) or ""

    async def renew_lease(self, *, task_id: UUID, runner_id: str, lease_seconds: int) -> bool:
        return await self._update_owned_running(
            task_id=task_id,
            runner_id=runner_id,
            values={"lease_expires_at": datetime.now(UTC) + timedelta(seconds=lease_seconds)},
        )

    async def complete(self, *, task_id: UUID, runner_id: str, result: dict) -> bool:
        return await self._update_owned_running(
            task_id=task_id,
            runner_id=runner_id,
            values={
                "status": SystemTaskStatus.succeeded,
                "active_key": case(
                    (SystemTask.task_type.in_(ACTIVE_KEY_RETAINING_TASK_TYPES), SystemTask.active_key), else_=None
                ),
                "completed_at": datetime.now(UTC),
                "lease_expires_at": None,
                "progress": 100,
                "result": result,
            },
        )

    async def fail(self, *, task_id: UUID, runner_id: str, message: str) -> bool:
        return await self._update_owned_running(
            task_id=task_id,
            runner_id=runner_id,
            values={
                "status": SystemTaskStatus.failed,
                "active_key": None,
                "completed_at": datetime.now(UTC),
                "lease_expires_at": None,
                "error": {"code": "system_task_failed", "message": message},
            },
        )

    async def _update_owned_running(self, *, task_id: UUID, runner_id: str, values: dict) -> bool:
        now = datetime.now(UTC)
        result = await self._session.execute(
            update(SystemTask)
            .where(
                SystemTask.id == task_id,
                SystemTask.status == SystemTaskStatus.running,
                SystemTask.runner_id == runner_id,
                SystemTask.lease_expires_at > now,
            )
            .values(**values)
        )
        return result.rowcount == 1
