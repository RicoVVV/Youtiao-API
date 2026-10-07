"""服务器资源采集用例：采样、落库、评估告警并清理超期数据。

采集窗口按 1 分钟对齐，同一窗口重复执行不会重复采样。
调度延迟跨过窗口时跳过缺失的窗口而不做回补：资源指标是"当时状态"，
事后无法还原真实采样值，伪造一条快照比在趋势上留下缺口更糟。
"""

import logging
from datetime import datetime, timedelta

from sqlmodel import Session

from app.core.config import Settings
from app.infrastructure.system_metrics import sample_system_metrics
from app.modules.monitoring.application.alerting import MonitorAlertApplicationService
from app.modules.monitoring.application.server_metrics import build_snapshot_values
from app.modules.monitoring.application.window import floor_server_window
from app.modules.monitoring.crud.alert_crud import MonitorAlertCrud
from app.modules.monitoring.crud.server_metric_crud import ServerMetricCrud

logger = logging.getLogger(__name__)


class ServerMetricCollectionService:
    """采集宿主整机资源，写入快照并驱动资源告警评估。"""

    def __init__(self, session: Session, settings: Settings) -> None:
        """绑定调用方提供的事务会话与运行配置。"""

        self._session = session
        self._settings = settings
        self._snapshots = ServerMetricCrud(session)
        self._alerts = MonitorAlertCrud(session)
        self._alerting = MonitorAlertApplicationService(session)

    def collect(self, *, now: datetime) -> dict[str, int]:
        """采集一次宿主资源、写入当前分钟窗口、评估资源告警并清理超期数据。"""

        window_start = floor_server_window(now)
        counters = {"collected": 0, "skipped": 0}
        if self._snapshots.get_by_window(window_start=window_start) is None:
            sample = sample_system_metrics(self._settings)
            previous = self._snapshots.get_previous(window_start=window_start)
            snapshot = self._snapshots.replace_window(
                window_start=window_start,
                values=build_snapshot_values(window_start=window_start, sample=sample, previous=previous),
            )
            counters["collected"] = 1
            counters.update(self._alerting.evaluate_server_window(window_start=window_start, snapshot=snapshot))
        else:
            counters["skipped"] = 1
        counters["snapshots_removed"] = self._snapshots.delete_expired(
            before=now - timedelta(days=self._settings.monitoring_server_metric_retention_days)
        )
        counters["alerts_removed"] = self._alerts.delete_expired(
            before=now - timedelta(days=self._settings.monitoring_alert_retention_days)
        )
        logger.info("服务器资源采集完成 window=%s %s", window_start.isoformat(), counters)
        return counters
