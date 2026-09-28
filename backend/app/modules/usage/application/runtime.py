"""用量统计系统任务 runner，按日幂等重建用量统计。"""

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from app.core.database import get_session_factory
from app.modules.system_tasks.application.services import AsyncSystemTaskApplicationService
from app.modules.usage.application.statistics_services import UsageStatisticsApplicationService


class UsageStatisticsSystemTaskRunner:
    """负责按日重建用量统计，任务以日期为活动键保证每日唯一。"""

    task_type = "usage_statistics_rebuild"

    async def schedule(self, service: AsyncSystemTaskApplicationService) -> None:
        stat_date = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
        await service.enqueue(task_type=self.task_type, active_key=f"{self.task_type}:{stat_date}")

    async def run(self) -> dict[str, int]:
        return await asyncio.to_thread(self._rebuild)

    @staticmethod
    def _rebuild() -> dict[str, int]:
        with get_session_factory()() as session:
            rows = UsageStatisticsApplicationService(session).rebuild_recent_daily_statistics()
            session.commit()
            return {"statistics_rows": rows}
