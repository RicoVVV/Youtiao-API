from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import case, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlmodel import Session

from app.modules.system_tasks.model.system_task import SystemTask, SystemTaskStatus


class SystemTaskCrud:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_poll_if_absent(self) -> SystemTask | None:
        return self._create_if_absent(task_type="async_task_poll")

    def create_usage_statistics_if_absent(self) -> SystemTask | None:
        stat_date = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
        return self._create_if_absent(
            task_type="usage_statistics_rebuild", active_key=f"usage_statistics_rebuild:{stat_date}"
        )

    def _create_if_absent(self, *, task_type: str, active_key: str | None = None) -> SystemTask | None:
        active_key = active_key or task_type
        statement = (
            insert(SystemTask)
            .values(task_type=task_type, active_key=active_key, status=SystemTaskStatus.pending)
            .on_conflict_do_nothing(index_elements=["active_key"])
            .returning(SystemTask)
        )
        return self._session.execute(statement).scalar_one_or_none()

    def claim_next(self, *, runner_id: str, lease_seconds: int) -> SystemTask | None:
        now = datetime.now(UTC)
        task = self._session.scalar(
            select(SystemTask)
            .where(
                or_(
                    SystemTask.status == SystemTaskStatus.pending,
                    (SystemTask.status == SystemTaskStatus.running) & (SystemTask.lease_expires_at <= now),
                )
            )
            .order_by(SystemTask.created_at, SystemTask.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if task is None:
            return None
        task.status = SystemTaskStatus.running
        task.runner_id = runner_id
        task.started_at = now
        task.lease_expires_at = now + timedelta(seconds=lease_seconds)
        task.error = None
        return task

    def get(self, *, task_id) -> SystemTask | None:
        return self._session.get(SystemTask, task_id)

    def complete(self, *, task_id, runner_id: str, result: dict) -> bool:
        now = datetime.now(UTC)
        statement = (
            update(SystemTask)
            .where(
                SystemTask.id == task_id,
                SystemTask.status == SystemTaskStatus.running,
                SystemTask.runner_id == runner_id,
                SystemTask.lease_expires_at > now,
            )
            .values(
                status=SystemTaskStatus.succeeded,
                active_key=case(
                    (SystemTask.task_type != "usage_statistics_rebuild", None), else_=SystemTask.active_key
                ),
                completed_at=now,
                lease_expires_at=None,
                progress=100,
                result=result,
            )
        )
        return self._session.execute(statement).rowcount == 1

    def renew_lease(self, *, task_id, runner_id: str, lease_seconds: int) -> bool:
        now = datetime.now(UTC)
        result = self._session.execute(
            update(SystemTask)
            .where(
                SystemTask.id == task_id,
                SystemTask.status == SystemTaskStatus.running,
                SystemTask.runner_id == runner_id,
                SystemTask.lease_expires_at > now,
            )
            .values(lease_expires_at=now + timedelta(seconds=lease_seconds))
        )
        return result.rowcount == 1

    def fail(self, *, task_id, runner_id: str, message: str) -> bool:
        now = datetime.now(UTC)
        statement = (
            update(SystemTask)
            .where(
                SystemTask.id == task_id,
                SystemTask.status == SystemTaskStatus.running,
                SystemTask.runner_id == runner_id,
                SystemTask.lease_expires_at > now,
            )
            .values(
                status=SystemTaskStatus.failed,
                active_key=None,
                completed_at=now,
                lease_expires_at=None,
                error={"code": "system_task_failed", "message": message},
            )
        )
        return self._session.execute(statement).rowcount == 1
