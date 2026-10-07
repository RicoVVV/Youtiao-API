"""系统任务应用服务，负责通用任务的幂等入队与租约生命周期。"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.system_tasks.crud.async_ import AsyncSystemTaskCrud
from app.modules.system_tasks.model.system_task import SystemTask


class AsyncSystemTaskApplicationService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def enqueue(self, *, task_type: str, active_key: str | None = None) -> None:
        """幂等入队一类系统任务，同一活动键已存在时不重复创建。"""

        async with self._session_factory() as session:
            await AsyncSystemTaskCrud(session).create_if_absent(task_type=task_type, active_key=active_key)
            await session.commit()

    async def claim_next(self, *, runner_id: str, lease_seconds: int) -> SystemTask | None:
        async with self._session_factory() as session:
            task = await AsyncSystemTaskCrud(session).claim_next(runner_id=runner_id, lease_seconds=lease_seconds)
            await session.commit()
            return task

    async def renew_lease(self, *, task_id: UUID, runner_id: str, lease_seconds: int) -> bool:
        async with self._session_factory() as session:
            result = await AsyncSystemTaskCrud(session).renew_lease(
                task_id=task_id, runner_id=runner_id, lease_seconds=lease_seconds
            )
            await session.commit()
            return result

    async def complete(self, *, task_id: UUID, runner_id: str, result: dict) -> bool:
        async with self._session_factory() as session:
            completed = await AsyncSystemTaskCrud(session).complete(task_id=task_id, runner_id=runner_id, result=result)
            await session.commit()
            return completed

    async def fail(self, *, task_id: UUID, runner_id: str, message: str) -> bool:
        async with self._session_factory() as session:
            failed = await AsyncSystemTaskCrud(session).fail(task_id=task_id, runner_id=runner_id, message=message)
            await session.commit()
            return failed
