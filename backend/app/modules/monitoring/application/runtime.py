"""监控相关系统任务 runner。

分组聚合任务以 5 分钟窗口起点、服务器资源采集以 1 分钟窗口起点作为活动键，
保证同一窗口只入队一次；执行时任务自行推导当前目标窗口，
因此调度延迟只会表现为窗口缺口，不会重复统计。
"""

import asyncio
from datetime import UTC, datetime

from app.core.config import get_settings
from app.core.database import get_session_factory
from app.modules.monitoring.application.aggregation import GroupMonitorAggregationService
from app.modules.monitoring.application.collection import ServerMetricCollectionService
from app.modules.monitoring.application.window import floor_server_window, newest_window
from app.modules.system_tasks.application.services import AsyncSystemTaskApplicationService


class GroupMonitorSystemTaskRunner:
    """负责按 5 分钟窗口聚合分组监控快照并评估告警。"""

    task_type = "group_monitor_aggregate"

    async def schedule(self, service: AsyncSystemTaskApplicationService) -> None:
        """为当前目标窗口幂等入队聚合任务。"""

        window_start = newest_window(datetime.now(UTC))
        await service.enqueue(task_type=self.task_type, active_key=f"{self.task_type}:{window_start.isoformat()}")

    async def run(self) -> dict[str, int]:
        """在线程池内执行窗口聚合，避免阻塞调度事件循环。"""

        return await asyncio.to_thread(self._aggregate)

    @staticmethod
    def _aggregate() -> dict[str, int]:
        """在独立事务内完成快照写入、告警评估与超期清理。"""

        with get_session_factory()() as session:
            counters = GroupMonitorAggregationService(session, get_settings()).aggregate(now=datetime.now(UTC))
            session.commit()
            return counters


class ServerMetricSystemTaskRunner:
    """负责按 1 分钟窗口采集宿主整机资源并评估资源告警。"""

    task_type = "server_metric_collect"

    async def schedule(self, service: AsyncSystemTaskApplicationService) -> None:
        """为当前采样窗口幂等入队采集任务。"""

        window_start = floor_server_window(datetime.now(UTC))
        await service.enqueue(task_type=self.task_type, active_key=f"{self.task_type}:{window_start.isoformat()}")

    async def run(self) -> dict[str, int]:
        """在线程池内执行采样，文件读取与 psutil 调用均为阻塞操作。"""

        return await asyncio.to_thread(self._collect)

    @staticmethod
    def _collect() -> dict[str, int]:
        """在独立事务内完成采样、快照写入、告警评估与超期清理。"""

        with get_session_factory()() as session:
            counters = ServerMetricCollectionService(session, get_settings()).collect(now=datetime.now(UTC))
            session.commit()
            return counters
