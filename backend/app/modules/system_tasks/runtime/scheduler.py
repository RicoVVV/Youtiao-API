"""通用系统任务运行时，基于领导租约的 runner 调度循环。"""

import asyncio
import logging
from collections.abc import Iterable
from contextlib import suppress
from uuid import UUID, uuid4

from app.core.config import get_settings
from app.core.database import get_async_engine, get_async_session_factory
from app.modules.system_tasks.application.services import AsyncSystemTaskApplicationService
from app.modules.system_tasks.runtime.runner import SystemTaskRunner
from app.modules.system_tasks.runtime.scheduler_leader import SchedulerLeaderLease

logger = logging.getLogger(__name__)

MAX_TASKS_PER_ITERATION = 20
"""单轮最多领取执行的任务数，防止积压异常时长时间不让出调度循环。"""


class SystemTaskRuntime:
    """按注册的 runner 调度系统任务，同一时刻仅由领导实例执行。"""

    def __init__(self, runners: Iterable[SystemTaskRunner]) -> None:
        self._runner_id = str(uuid4())
        self._runners = {runner.task_type: runner for runner in runners}
        self._task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()
        self._leader_lease = SchedulerLeaderLease(get_async_engine())

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="system-task-runner")

    async def stop(self) -> None:
        self._stopping.set()
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
        await self._leader_lease.release()

    async def _run(self) -> None:
        settings = get_settings()
        try:
            while not self._stopping.is_set():
                try:
                    if await self._leader_lease.try_acquire():
                        await self._run_leader_iteration(settings.system_task_lock_ttl_seconds)
                except Exception:
                    logger.exception("系统任务调度循环异常", extra={"runner_id": self._runner_id})
                await asyncio.sleep(settings.system_task_scheduler_interval_seconds)
        finally:
            await self._leader_lease.release()

    async def _run_leader_iteration(self, lease_seconds: int) -> None:
        """为所有 runner 入队，并连续领取执行待办任务直到队列为空。

        一轮内连续领取而不是只领一条：每轮固定 30 秒的前提下，只领一条会让每个任务的
        实际执行间隔随任务数量线性拉长，分钟级任务无法保证节奏。
        领取顺序为入队顺序，因此被单轮上限截断的任务会在下一轮优先被领到。
        """

        service = AsyncSystemTaskApplicationService(get_async_session_factory())
        for runner in self._runners.values():
            await runner.schedule(service)
        for _ in range(MAX_TASKS_PER_ITERATION):
            system_task = await service.claim_next(runner_id=self._runner_id, lease_seconds=lease_seconds)
            if system_task is None:
                return
            runner = self._runners.get(system_task.task_type)
            if runner is None:
                message = f"未注册的系统任务类型：{system_task.task_type}"
                logger.error(message, extra={"system_task_id": system_task.id, "runner_id": self._runner_id})
                await service.fail(task_id=system_task.id, runner_id=self._runner_id, message=message)
                continue
            try:
                result = await self._run_with_lease_heartbeat(service, system_task.id, lease_seconds, runner)
            except Exception as exc:
                logger.exception(
                    "系统任务执行异常",
                    extra={"system_task_id": system_task.id, "runner_id": self._runner_id},
                )
                await service.fail(task_id=system_task.id, runner_id=self._runner_id, message=str(exc))
            else:
                await service.complete(task_id=system_task.id, runner_id=self._runner_id, result=result)

    async def _run_with_lease_heartbeat(
        self,
        service: AsyncSystemTaskApplicationService,
        task_id: UUID,
        lease_seconds: int,
        runner: SystemTaskRunner,
    ) -> dict[str, int]:
        run_task = asyncio.create_task(runner.run())
        heartbeat_seconds = max(1, lease_seconds // 2)
        while not run_task.done():
            done, _ = await asyncio.wait({run_task}, timeout=heartbeat_seconds)
            if done:
                break
            renewed = await service.renew_lease(task_id=task_id, runner_id=self._runner_id, lease_seconds=lease_seconds)
            if not renewed:
                raise RuntimeError("系统任务租约已失效")
        return await run_task
