"""监控相关系统任务 runner。

分组聚合任务以 5 分钟窗口起点、服务器资源采集以 1 分钟窗口起点作为活动键，
保证同一窗口只入队一次；执行时任务自行推导当前目标窗口，
因此调度延迟只会表现为窗口缺口，不会重复统计。
"""

import asyncio
import logging
from datetime import UTC, datetime

from app.core.config import get_settings
from app.core.database import get_async_session_factory, get_session_factory
from app.modules.channels.runtime.task_gate import acquire_window
from app.modules.monitoring.application.aggregation import GroupMonitorAggregationService
from app.modules.monitoring.application.collection import ServerMetricCollectionService
from app.modules.monitoring.application.probe import GroupProbeApplicationService
from app.modules.monitoring.application.traffic_settings import MonitorTrafficSettingsApplicationService
from app.modules.monitoring.application.window import floor_server_window, newest_window
from app.modules.monitoring.model import MONITOR_MODE_PROBE
from app.modules.system_tasks.application.services import AsyncSystemTaskApplicationService

logger = logging.getLogger(__name__)


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


class GroupMonitorProbeSystemTaskRunner:
    """嗅探模式下按分钟向每个分组发送最小文本请求。"""

    task_type = "group_monitor_probe"

    async def schedule(self, service: AsyncSystemTaskApplicationService) -> None:
        """仅在文本类型使用嗅探模式时按管理员配置的周期幂等入队探测任务。"""

        try:
            text_mode, interval = await asyncio.to_thread(self._read_settings)
        except Exception:
            logger.warning("分组嗅探模式读取失败，跳过本轮入队", exc_info=True)
            return
        if text_mode != MONITOR_MODE_PROBE:
            return
        # 周期变化时使用新的闸门键，避免旧周期的长 TTL 阻塞新配置立即生效。
        if not acquire_window(f"group-monitor-probe:{interval}", interval):
            return
        await service.enqueue(task_type=self.task_type)

    async def run(self) -> dict[str, int]:
        """执行一轮分组文本嗅探。"""

        return await GroupProbeApplicationService(get_async_session_factory()).probe_all()

    @staticmethod
    def _read_settings() -> tuple[str, int]:
        """读取文本类型当前模式与嗅探周期。"""

        with get_session_factory()() as session:
            settings = MonitorTrafficSettingsApplicationService(session)
            return settings.current_text_mode(), settings.current_probe_interval_seconds()
