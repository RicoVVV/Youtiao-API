"""告警阈值评估与状态流转。

评估面向三类目标：分组整体、「分组 × 渠道」与服务器资源。
评估严格面向单个窗口：同一窗口重复执行不会重复累计连续命中，也不会重复推送。
"""

import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlmodel import Session

from app.core.errors import NotFoundError, ValidationError
from app.modules.monitoring.application.contracts import AlertAtTargets, AlertEvaluationTarget, AlertThresholds
from app.modules.monitoring.application.notification import SERVER_TARGET_NAME, DingTalkNotifier
from app.modules.monitoring.application.resource_settings import MonitorResourceSettingsApplicationService
from app.modules.monitoring.application.settings import MonitorSettingsApplicationService
from app.modules.monitoring.crud.alert_crud import MonitorAlertCrud
from app.modules.monitoring.crud.reference_crud import MonitoringReferenceCrud
from app.modules.monitoring.model import (
    MonitorAlert,
    MonitorAlertMetric,
    MonitorAlertNotificationStatus,
    MonitorAlertStatus,
    MonitorResourceRule,
    ServerMetricSnapshot,
)
from app.modules.monitoring.model.metric_bucket import MetricBucket

logger = logging.getLogger(__name__)

TEXT_REQUEST_TYPE = "text"
"""只有文本请求记录首 token 耗时，因此该指标仅对文本类型评估。"""

RESOURCE_SAMPLE_COUNT = 1
"""每次资源采样只有一个样本，资源告警不做最小样本数过滤。"""


class MonitorAlertApplicationService:
    """按窗口评估阈值，驱动状态流转并按需推送钉钉通知。"""

    def __init__(self, session: Session) -> None:
        """绑定调用方提供的事务会话。"""

        self._session = session
        self._alerts = MonitorAlertCrud(session)
        self._settings = MonitorSettingsApplicationService(session)
        self._resource_settings = MonitorResourceSettingsApplicationService(session)
        self._references = MonitoringReferenceCrud(session)
        self._group_names: dict[int, str] = {}
        self._channel_names: dict[UUID, str] = {}

    def evaluate_window(
        self,
        *,
        window_start: datetime,
        group_buckets: dict[tuple[int, str], MetricBucket],
        channel_buckets: dict[tuple[int, UUID, str], MetricBucket],
    ) -> dict[str, int]:
        """评估一个窗口的分组级与渠道级指标，返回各类状态流转的计数。"""

        global_rule, overrides = self._settings.evaluation_rules()
        notification = self._settings.current_notification()
        notifier = DingTalkNotifier(notification)
        targets = self._iter_targets(group_buckets, channel_buckets)
        self._preload_names(targets)
        counters = {"evaluated": 0, "created": 0, "opened": 0, "resolved": 0, "removed": 0}
        for target in targets:
            rule = overrides.get(target.group_id, global_rule)
            if not rule.enabled:
                continue
            thresholds = AlertThresholds.from_rule(rule)
            if target.bucket.sample_count < thresholds.min_sample_count:
                continue
            counters["evaluated"] += 1
            at = AlertAtTargets.from_rules(rule, fallback=global_rule)
            for metric, value, threshold, hit in _metric_results(
                request_type=target.request_type, bucket=target.bucket, thresholds=thresholds
            ):
                outcome = self._apply_metric(
                    window_start=window_start,
                    group_id=target.group_id,
                    channel_id=target.channel_id,
                    metric=metric,
                    value=value,
                    threshold=threshold,
                    sample_count=target.bucket.sample_count,
                    required_hits=thresholds.consecutive_hits,
                    hit=hit,
                    notifier=notifier,
                    at=at,
                    notify_on_resolved=notification.notify_on_resolved,
                    silence_minutes=notification.silence_minutes,
                )
                if outcome in counters:
                    counters[outcome] += 1
        return counters

    def evaluate_server_window(self, *, window_start: datetime, snapshot: ServerMetricSnapshot) -> dict[str, int]:
        """评估一个采样窗口的服务器资源指标，返回各类状态流转的计数。"""

        rule = self._resource_settings.current_rule()
        counters = {"evaluated": 0, "created": 0, "opened": 0, "resolved": 0, "removed": 0}
        if not rule.enabled:
            return counters
        notification = self._settings.current_notification()
        notifier = DingTalkNotifier(notification)
        global_rule, _ = self._settings.evaluation_rules()
        at = AlertAtTargets.from_rules(global_rule)
        for metric, value, threshold in _resource_metric_results(rule=rule, snapshot=snapshot):
            counters["evaluated"] += 1
            outcome = self._apply_metric(
                window_start=window_start,
                group_id=None,
                channel_id=None,
                metric=metric,
                value=value,
                threshold=threshold,
                sample_count=RESOURCE_SAMPLE_COUNT,
                required_hits=rule.consecutive_hits,
                hit=value > threshold,
                notifier=notifier,
                at=at,
                notify_on_resolved=notification.notify_on_resolved,
                silence_minutes=notification.silence_minutes,
            )
            if outcome in counters:
                counters[outcome] += 1
        return counters

    def _apply_metric(
        self,
        *,
        window_start: datetime,
        group_id: int | None,
        channel_id: UUID | None,
        metric: MonitorAlertMetric,
        value: Decimal,
        threshold: Decimal,
        sample_count: int,
        required_hits: int,
        hit: bool,
        notifier: DingTalkNotifier,
        at: AlertAtTargets,
        notify_on_resolved: bool,
        silence_minutes: int,
    ) -> str:
        """按状态机处理单个指标的命中结果，返回本次动作。"""

        current = self._alerts.get_current(group_id=group_id, channel_id=channel_id, metric=metric)
        if current is not None and current.last_window_start >= window_start:
            return "skipped"
        now = datetime.now(UTC)
        measurements = {
            "last_window_start": window_start,
            "sample_count": sample_count,
            "actual_value": value,
            "threshold_value": threshold,
        }
        if current is None or current.status == MonitorAlertStatus.resolved:
            if not hit:
                return "skipped"
            return self._start_event(
                group_id=group_id,
                channel_id=channel_id,
                metric=metric,
                measurements=measurements,
                required_hits=required_hits,
                notifier=notifier,
                at=at,
                now=now,
            )
        if not hit:
            return self._settle_event(
                current=current,
                measurements=measurements,
                notifier=notifier,
                at=at,
                notify_on_resolved=notify_on_resolved,
                now=now,
            )
        hits = current.consecutive_hits + 1
        self._alerts.update(current, {**measurements, "consecutive_hits": hits})
        if current.status == MonitorAlertStatus.pending and hits >= required_hits:
            self._promote(alert=current, notifier=notifier, at=at, now=now)
            return "opened"
        if current.status == MonitorAlertStatus.open:
            self._push(
                alert=current,
                notifier=notifier,
                at=at,
                resolved=False,
                silence_minutes=silence_minutes,
                now=now,
                force=False,
            )
        return "updated"

    def _start_event(
        self,
        *,
        group_id: int | None,
        channel_id: UUID | None,
        metric: MonitorAlertMetric,
        measurements: dict,
        required_hits: int,
        notifier: DingTalkNotifier,
        at: AlertAtTargets,
        now: datetime,
    ) -> str:
        """新建告警事件；连续命中要求为 1 时直接进入已触发状态。"""

        alert = self._alerts.create(
            {
                "group_id": group_id,
                "channel_id": channel_id,
                "metric": metric,
                "status": MonitorAlertStatus.pending,
                "first_window_start": measurements["last_window_start"],
                "consecutive_hits": 1,
                **measurements,
            }
        )
        if required_hits > 1:
            return "created"
        self._promote(alert=alert, notifier=notifier, at=at, now=now)
        return "opened"

    def _settle_event(
        self,
        *,
        current: MonitorAlert,
        measurements: dict,
        notifier: DingTalkNotifier,
        at: AlertAtTargets,
        notify_on_resolved: bool,
        now: datetime,
    ) -> str:
        """指标恢复正常：候选事件直接删除，已触发或人工处置的事件转为已恢复。"""

        if current.status == MonitorAlertStatus.pending:
            self._alerts.remove(current)
            return "removed"
        should_notify = notify_on_resolved and current.status == MonitorAlertStatus.open
        self._alerts.update(
            current,
            {
                **measurements,
                "status": MonitorAlertStatus.resolved,
                "resolved_at": now,
                "consecutive_hits": 0,
            },
        )
        if should_notify:
            self._push(
                alert=current,
                notifier=notifier,
                at=at,
                resolved=True,
                silence_minutes=0,
                now=now,
                force=True,
            )
        return "resolved"

    def _promote(self, *, alert: MonitorAlert, notifier: DingTalkNotifier, at: AlertAtTargets, now: datetime) -> None:
        """把候选事件升级为已触发并立即推送。"""

        self._alerts.update(
            alert,
            {
                "status": MonitorAlertStatus.open,
                "triggered_at": now,
                "resolved_at": None,
                "notification_status": MonitorAlertNotificationStatus.pending,
            },
        )
        logger.warning(
            "监控告警触发 group_id=%s channel_id=%s metric=%s actual=%s threshold=%s",
            alert.group_id,
            alert.channel_id,
            alert.metric.value,
            alert.actual_value,
            alert.threshold_value,
        )
        self._push(alert=alert, notifier=notifier, at=at, resolved=False, silence_minutes=0, now=now, force=True)

    def _push(
        self,
        *,
        alert: MonitorAlert,
        notifier: DingTalkNotifier,
        at: AlertAtTargets,
        resolved: bool,
        silence_minutes: int,
        now: datetime,
        force: bool,
    ) -> None:
        """推送告警或恢复通知，静默期内跳过，推送结果写回告警行。"""

        if not force and _in_silence_period(alert=alert, now=now, silence_minutes=silence_minutes):
            return
        result = notifier.send_alert(
            alert=alert,
            target_label=self._target_label(alert),
            channel_name=self._channel_name(alert.channel_id),
            resolved=resolved,
            at=at,
        )
        values: dict = {"notification_status": result.status, "notification_error": result.error}
        if result.status == MonitorAlertNotificationStatus.sent:
            values["notified_at"] = now
        self._alerts.update(alert, values)

    def mark_status(self, *, alert_id: UUID, status: MonitorAlertStatus) -> dict:
        """人工确认或忽略一条未结束的告警，返回处置结果。

        已结束的告警不允许再处置：人工态会抑制该目标后续窗口的推送，
        因此把已恢复的告警改成人工态会错误地压掉下一次真实故障。
        """

        alert = self._alerts.get(alert_id)
        if alert is None:
            raise NotFoundError("告警记录不存在")
        if alert.status not in (MonitorAlertStatus.pending, MonitorAlertStatus.open):
            raise ValidationError("该告警已结束，无需处置")
        now = datetime.now(UTC)
        try:
            self._alerts.update(alert, {"status": status, "acknowledged_at": now})
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
        return {"alert_id": str(alert.id), "status": alert.status.value, "acknowledged_at": now.isoformat()}

    def _preload_names(self, targets: list[AlertEvaluationTarget]) -> None:
        """批量预加载评估涉及的分组与渠道名称，避免逐条查询。"""

        self._group_names = self._references.group_names({target.group_id for target in targets})
        self._channel_names = self._references.channel_names(
            {target.channel_id for target in targets if target.channel_id is not None}
        )

    def _target_label(self, alert: MonitorAlert) -> str:
        """资源告警以服务器为目标名称，业务告警使用分组名称。"""

        if alert.group_id is None:
            return SERVER_TARGET_NAME
        return self._group_name(alert.group_id)

    def _group_name(self, group_id: int) -> str:
        """读取预加载的分组名称，缺失时回退为标识文案。"""

        return self._group_names.get(group_id) or f"分组 {group_id}"

    def _channel_name(self, channel_id: UUID | None) -> str | None:
        """读取预加载的渠道名称，分组级告警返回 ``None``。"""

        if channel_id is None:
            return None
        return self._channel_names.get(channel_id) or str(channel_id)

    @staticmethod
    def _iter_targets(
        group_buckets: dict[tuple[int, str], MetricBucket],
        channel_buckets: dict[tuple[int, UUID, str], MetricBucket],
    ) -> list[AlertEvaluationTarget]:
        """合并分组级与渠道级目标，分组级目标先于渠道级目标。"""

        targets = [
            AlertEvaluationTarget(group_id=group_id, channel_id=None, request_type=request_type, bucket=bucket)
            for (group_id, request_type), bucket in group_buckets.items()
        ]
        targets.extend(
            AlertEvaluationTarget(group_id=group_id, channel_id=channel_id, request_type=request_type, bucket=bucket)
            for (group_id, channel_id, request_type), bucket in channel_buckets.items()
        )
        return targets


def _metric_results(
    *, request_type: str, bucket: MetricBucket, thresholds: AlertThresholds
) -> list[tuple[MonitorAlertMetric, Decimal, Decimal, bool]]:
    """按指标的阈值配置计算「实际值、阈值、是否命中」。

    阈值为空表示不评估该指标；指标没有可计算值（例如没有成功请求）时同样跳过。
    """

    results: list[tuple[MonitorAlertMetric, Decimal, Decimal, bool]] = []
    if thresholds.success_rate_min is not None and bucket.success_rate is not None:
        value = Decimal(str(bucket.success_rate))
        results.append(
            (MonitorAlertMetric.success_rate, value, thresholds.success_rate_min, value < thresholds.success_rate_min)
        )
    if thresholds.average_duration_ms_max is not None and bucket.average_duration_ms is not None:
        value = Decimal(bucket.average_duration_ms)
        threshold = Decimal(thresholds.average_duration_ms_max)
        results.append((MonitorAlertMetric.average_duration_ms, value, threshold, value > threshold))
    if (
        request_type == TEXT_REQUEST_TYPE
        and thresholds.average_first_token_ms_max is not None
        and bucket.average_first_token_ms is not None
    ):
        value = Decimal(bucket.average_first_token_ms)
        threshold = Decimal(thresholds.average_first_token_ms_max)
        results.append((MonitorAlertMetric.average_first_token_ms, value, threshold, value > threshold))
    return results


def _resource_metric_results(
    *, rule: MonitorResourceRule, snapshot: ServerMetricSnapshot
) -> list[tuple[MonitorAlertMetric, Decimal, Decimal]]:
    """按资源规则计算「指标、实际值、阈值」。

    阈值为空表示不评估该指标；指标没有可计算值（首次采集、宿主未启用交换分区、
    磁盘路径不可用）时同样跳过。
    """

    candidates = (
        (MonitorAlertMetric.cpu_usage, rule.cpu_usage_max, snapshot.cpu_usage_percent),
        (MonitorAlertMetric.memory_usage, rule.memory_usage_max, snapshot.memory_usage_percent),
        (MonitorAlertMetric.swap_usage, rule.swap_usage_max, snapshot.swap_usage_percent),
        (MonitorAlertMetric.disk_usage, rule.disk_usage_max, snapshot.max_disk_usage_percent),
    )
    return [
        (metric, actual, threshold)
        for metric, threshold, actual in candidates
        if threshold is not None and actual is not None
    ]


def _in_silence_period(*, alert: MonitorAlert, now: datetime, silence_minutes: int) -> bool:
    """判断该告警是否仍在重复推送的静默期内。"""

    if alert.notified_at is None:
        return False
    return now - alert.notified_at < timedelta(minutes=silence_minutes)
