"""系统任务 runner 契约，用于解耦通用调度与具体任务执行。"""

from typing import Protocol

from app.modules.system_tasks.application.services import AsyncSystemTaskApplicationService


class SystemTaskRunner(Protocol):
    """一类系统任务的入队与执行契约。

    ``task_type`` 声明该 runner 负责的任务类型；``schedule`` 按需幂等入队；``run`` 执行已认领任务并返回结果快照。
    """

    task_type: str

    async def schedule(self, service: AsyncSystemTaskApplicationService) -> None: ...

    async def run(self) -> dict[str, int]: ...
