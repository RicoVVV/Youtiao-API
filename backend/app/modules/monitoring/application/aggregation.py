"""窗口聚合用例：写入分组级快照、评估告警并清理超期数据。

按 ``completed_at`` 归属窗口后，跨窗口完成的异步视频会落在它完成时刻的窗口；
聚合任务因此只需处理"滞后一个窗口"的目标窗口，并对调度延迟造成的缺口做有限回补。
"""

import logging
from datetime import datetime, timedelta

from sqlmodel import Session

from app.core.config import Settings
from app.modules.monitoring.application.alerting import MonitorAlertApplicationService
from app.modules.monitoring.application.window import (
    CATCH_UP_WINDOWS,
    newest_window,
    recent_windows,
    window_end,
)
from app.modules.monitoring.crud.alert_crud import MonitorAlertCrud
from app.modules.monitoring.crud.snapshot_crud import SnapshotCrud
from app.modules.monitoring.model.metric_bucket import MetricBucket

logger = logging.getLogger(__name__)


class GroupMonitorAggregationService:
    """按窗口写入分组级快照并驱动告警评估。"""

    def __init__(self, session: Session, settings: Settings) -> None:
        """绑定调用方提供的事务会话与运行配置。"""

        self._session = session
        self._settings = settings
        self._snapshots = SnapshotCrud(session)
        self._alerts = MonitorAlertCrud(session)
        self._alerting = MonitorAlertApplicationService(session)

    def aggregate(self, *, now: datetime) -> dict[str, int]:
        """回补缺失窗口的快照、评估最新窗口的告警并清理超期数据。"""

        newest = newest_window(now)
        counters = self._write_missing_windows(windows=recent_windows(newest=newest, count=CATCH_UP_WINDOWS))
        counters.update(self._evaluate_newest_window(newest))
        counters["snapshots_removed"] = self._snapshots.delete_expired(
            before=now - timedelta(days=self._settings.monitoring_snapshot_retention_days)
        )
        counters["alerts_removed"] = self._alerts.delete_expired(
            before=now - timedelta(days=self._settings.monitoring_alert_retention_days)
        )
        logger.info("分组监控窗口聚合完成 newest=%s %s", newest.isoformat(), counters)
        return counters

    def _write_missing_windows(self, *, windows: list[datetime]) -> dict[str, int]:
        """为尚无快照的窗口写入分组级计数，已聚合的窗口跳过。"""

        written = 0
        aggregated = 0
        for window_start in windows:
            if self._snapshots.window_has_rows(window_start=window_start):
                continue
            buckets = self._snapshots.aggregate_by_group(start_at=window_start, end_at=window_end(window_start))
            written += self._snapshots.replace_window(window_start=window_start, buckets=buckets)
            aggregated += 1
        return {"snapshot_rows": written, "snapshot_windows": aggregated}

    def _evaluate_newest_window(self, window_start: datetime) -> dict[str, int]:
        """评估最新窗口的分组级与渠道级指标。"""

        end_at = window_end(window_start)
        group_buckets = self._window_group_buckets(window_start=window_start, end_at=end_at)
        channel_buckets = self._snapshots.aggregate_by_channel(start_at=window_start, end_at=end_at)
        return self._alerting.evaluate_window(
            window_start=window_start,
            group_buckets=group_buckets,
            channel_buckets=channel_buckets,
        )

    def _window_group_buckets(self, *, window_start: datetime, end_at: datetime) -> dict[tuple[int, str], MetricBucket]:
        """读取窗口的分组级计数；窗口尚未落库时按当前数据即时聚合。"""

        rows = self._snapshots.list_window(window_start=window_start)
        if not rows:
            return self._snapshots.aggregate_by_group(start_at=window_start, end_at=end_at)
        return {(row.token_group_id, row.request_type): MetricBucket.from_snapshot(row) for row in rows}
