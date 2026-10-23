"""分组监控查询用例，服务于用户侧与管理侧只读接口。

返回结构按「图表即取即用」约定组织：列表接口返回字段平铺的一维数组，
趋势接口返回等长的 x 轴与序列；无样本时派生指标为 ``None`` 而不是 0。
"""

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlmodel import Session

from app.core.errors import NotFoundError
from app.modules.channels.crud.channels import ChannelCrud
from app.modules.monitoring.application.traffic_settings import MonitorTrafficSettingsApplicationService
from app.modules.monitoring.application.visibility_settings import MonitorUserVisibilityApplicationService
from app.modules.monitoring.application.window import (
    WINDOW_MINUTES,
    WINDOWS_PER_DAY,
    WINDOWS_PER_HOUR,
    newest_window,
    recent_windows,
    window_end,
)
from app.modules.monitoring.crud.alert_crud import MonitorAlertCrud
from app.modules.monitoring.crud.reference_crud import MonitoringReferenceCrud
from app.modules.monitoring.crud.snapshot_crud import TRACKED_REQUEST_TYPES, SnapshotCrud
from app.modules.monitoring.model import (
    MONITOR_MODE_PROBE,
    MONITOR_MODE_REAL,
    RESOURCE_ALERT_METRICS,
    MonitorAlertMetric,
    MonitorAlertStatus,
)
from app.modules.monitoring.model.metric_bucket import MetricBucket
from app.modules.user.crud.token_group_crud import TokenGroupCrud

LATEST_PERIOD = "latest"
LAST_24H_PERIOD = "last_24h"

TEXT_REQUEST_TYPE = "text"
"""只有文本请求记录首 token 耗时。"""

ALERT_SCOPE_GROUP = "group"
ALERT_SCOPE_SERVER = "server"

BUSINESS_ALERT_METRICS = (
    MonitorAlertMetric.success_rate,
    MonitorAlertMetric.average_duration_ms,
    MonitorAlertMetric.average_first_token_ms,
)
"""分组业务告警的指标集合，用于与服务器资源告警区分。"""

_REQUEST_TYPE_LABELS = {"text": "文本", "image": "图片", "video": "视频"}

_METRIC_SERIES = (
    ("success_rate", "ratio", "成功率"),
    ("average_duration_ms", "ms", "平均耗时"),
    ("average_first_token_ms", "ms", "平均首 token"),
)


class GroupMonitorQueryApplicationService:
    """分组监控的读取用例：最近窗口指标、区间汇总与窗口序列。"""

    def __init__(self, session: Session) -> None:
        """绑定调用方提供的事务会话。"""

        self._session = session
        self._snapshots = SnapshotCrud(session)
        self._alerts = MonitorAlertCrud(session)
        self._groups = TokenGroupCrud(session)
        self._channels = ChannelCrud(session)
        self._references = MonitoringReferenceCrud(session)
        self._traffic = MonitorTrafficSettingsApplicationService(session)

    def user_group_metrics(self, *, user_id: UUID, group_id: int | None) -> dict:
        """用户侧：返回当前用户可用、管理员允许展示且支持可见类型的指标。"""

        visibility = MonitorUserVisibilityApplicationService(self._session)
        modes = self._traffic.current_modes()
        request_types = visibility.visible_request_types()
        allowed_group_ids = visibility.restricted_group_ids()
        candidates = [
            group
            for group in self._groups.list_available_groups(user_id)
            if group_id in (None, group.id) and (allowed_group_ids is None or group.id in allowed_group_ids)
        ]
        supported = self._channels.list_group_model_types(group_ids=[group.id for group in candidates])
        visible_types = set(request_types)
        groups = [group for group in candidates if visible_types & set(supported.get(group.id, []))]
        if group_id is not None and not groups:
            raise NotFoundError("Token 分组不存在")
        return {
            **self._window_meta(),
            "modes": modes,
            "request_types": list(request_types),
            "items": self._group_items(groups=groups, with_alert_count=False, request_types=request_types, modes=modes),
        }

    def admin_group_metrics(self, *, group_id: int | None) -> dict:
        """管理侧：返回全部分组的最新窗口与近 24 小时指标。"""

        groups = [group for group in self._groups.list_groups() if group_id in (None, group.id)]
        if group_id is not None and not groups:
            raise NotFoundError("Token 分组不存在")
        modes = self._traffic.current_modes()
        request_types = TRACKED_REQUEST_TYPES
        return {
            **self._window_meta(),
            "modes": modes,
            "request_types": list(request_types),
            "items": self._group_items(groups=groups, with_alert_count=True, request_types=request_types, modes=modes),
        }

    def group_trend(self, *, group_id: int, request_type: str | None, hours: int, user_id: UUID | None = None) -> dict:
        """返回指定分组最近若干小时的 5 分钟粒度指标序列。

        每个请求类型按自己的模式取数：文本可能来自嗅探，图片与视频始终来自真实请求。
        传入 ``user_id`` 时按用户可用分组与管理员配置的可见范围做校验，用于用户侧接口。
        """

        group = self._resolve_group(group_id=group_id, user_id=user_id)
        modes = self._traffic.current_modes()
        if user_id is not None:
            visibility = MonitorUserVisibilityApplicationService(self._session)
            allowed_group_ids = visibility.restricted_group_ids()
            if allowed_group_ids is not None and group_id not in allowed_group_ids:
                raise NotFoundError("Token 分组不存在")
            allowed_request_types = visibility.visible_request_types()
            supported = set(self._channels.list_group_model_types(group_ids=[group_id]).get(group_id, []))
            allowed_request_types = tuple(
                current_type for current_type in allowed_request_types if current_type in supported
            )
            if not allowed_request_types:
                raise NotFoundError("监控指标不存在")
        else:
            allowed_request_types = TRACKED_REQUEST_TYPES
        if request_type is not None and request_type not in allowed_request_types:
            raise NotFoundError("监控指标不存在")
        request_types = [request_type] if request_type else list(allowed_request_types)
        newest = newest_window(datetime.now(UTC))
        windows = recent_windows(newest=newest, count=hours * WINDOWS_PER_HOUR)
        rows = self._snapshots.list_range(start_at=windows[0], end_at=windows[-1], group_ids=[group_id])
        buckets = {(row.mode, row.window_start, row.request_type): MetricBucket.from_snapshot(row) for row in rows}
        series = [
            _series_payload(
                request_type=current_type,
                mode=modes.get(current_type, MONITOR_MODE_REAL),
                metric=metric,
                unit=unit,
                label=label,
                windows=windows,
                buckets=buckets,
            )
            for current_type in request_types
            for metric, unit, label in _METRIC_SERIES
            if metric != "average_first_token_ms" or current_type == TEXT_REQUEST_TYPE
        ]
        return {
            "group_id": group.id,
            "group_name": group.name,
            "window_minutes": WINDOW_MINUTES,
            "modes": modes,
            "request_types": request_types,
            "x_axis": [window_start.isoformat() for window_start in windows],
            "summaries": _range_summaries(rows=rows, request_types=request_types, modes=modes),
            "series": series,
        }

    def channel_metrics(self, *, group_id: int | None) -> dict:
        """管理侧运维视图：返回最新窗口按各类型模式取数的渠道指标。"""

        newest = newest_window(datetime.now(UTC))
        modes = self._traffic.current_modes()
        real_buckets = self._snapshots.aggregate_by_channel(
            start_at=newest, end_at=window_end(newest), mode=MONITOR_MODE_REAL
        )
        probe_buckets = self._snapshots.aggregate_by_channel(
            start_at=newest, end_at=window_end(newest), mode=MONITOR_MODE_PROBE
        )
        buckets = {
            key: bucket
            for key, bucket in real_buckets.items()
            if modes.get(key[2], MONITOR_MODE_REAL) == MONITOR_MODE_REAL
        }
        buckets.update(
            {
                key: bucket
                for key, bucket in probe_buckets.items()
                if modes.get(key[2], MONITOR_MODE_REAL) == MONITOR_MODE_PROBE
            }
        )
        if group_id is not None:
            buckets = {key: bucket for key, bucket in buckets.items() if key[0] == group_id}
        group_names = self._references.group_names({key[0] for key in buckets})
        channel_names = self._references.channel_names({key[1] for key in buckets})
        items = [
            {
                "group_id": current_group_id,
                "group_name": group_names.get(current_group_id, f"分组 {current_group_id}"),
                "channel_id": str(channel_id),
                "channel_name": channel_names.get(channel_id, str(channel_id)),
                "request_type": request_type,
                "period": LATEST_PERIOD,
                "window_start": newest.isoformat(),
                "sample_count": bucket.sample_count,
                "success_rate": bucket.success_rate,
                "average_duration_ms": bucket.average_duration_ms,
                "average_first_token_ms": bucket.average_first_token_ms,
            }
            for (current_group_id, channel_id, request_type), bucket in sorted(
                buckets.items(), key=lambda item: (item[0][0], str(item[0][1]), item[0][2])
            )
        ]
        return {
            "items": items,
            "modes": modes,
            "window_start": newest.isoformat(),
            "window_minutes": WINDOW_MINUTES,
        }

    def alert_list(
        self,
        *,
        status: str | None,
        group_id: int | None,
        channel_id: UUID | None,
        metric: str | None,
        scope: str | None,
        hours: int | None,
        page: int,
        page_size: int,
    ) -> dict:
        """管理侧：分页返回告警记录，附分组与渠道展示名。

        ``scope`` 用于区分分组业务告警与服务器资源告警；指定 ``metric`` 时以该指标为准。
        """

        since = None if hours is None else datetime.now(UTC) - timedelta(hours=hours)
        total, alerts = self._alerts.list_page(
            page=page,
            page_size=page_size,
            status=MonitorAlertStatus(status) if status is not None else None,
            group_id=group_id,
            channel_id=channel_id,
            metrics=_resolve_metrics(scope=scope, metric=metric),
            since=since,
        )
        group_names = self._references.group_names({alert.group_id for alert in alerts})
        channel_names = self._references.channel_names(
            {alert.channel_id for alert in alerts if alert.channel_id is not None}
        )
        return {
            "items": [_alert_item(alert, group_names, channel_names) for alert in alerts],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def _group_items(
        self, *, groups: list, with_alert_count: bool, request_types: tuple[str, ...], modes: dict[str, str]
    ) -> list[dict]:
        """按「分组 × 请求类型 × 时段」构造字段平铺的指标行，每个类型取自己的数据模式。"""

        newest = newest_window(datetime.now(UTC))
        windows = recent_windows(newest=newest, count=WINDOWS_PER_DAY)
        group_ids = [group.id for group in groups]
        rows = self._snapshots.list_range(start_at=windows[0], end_at=windows[-1], group_ids=group_ids)
        latest_buckets: dict[tuple[str, int, str], MetricBucket] = {}
        day_buckets: dict[tuple[str, int, str], MetricBucket] = defaultdict(MetricBucket)
        for row in rows:
            key = (row.mode, row.token_group_id, row.request_type)
            bucket = MetricBucket.from_snapshot(row)
            if row.window_start == newest:
                latest_buckets[key] = bucket
            day_buckets[key] += bucket
        alert_counts = self._alerts.count_open_by_group()
        items: list[dict] = []
        for group in groups:
            for request_type in request_types:
                bucket_key = (modes.get(request_type, MONITOR_MODE_REAL), group.id, request_type)
                for period, bucket, window_start in (
                    (LATEST_PERIOD, latest_buckets.get(bucket_key), newest),
                    (LAST_24H_PERIOD, day_buckets.get(bucket_key), None),
                ):
                    item = _metric_item(
                        group=group,
                        request_type=request_type,
                        period=period,
                        window_start=window_start,
                        bucket=bucket,
                        alert_count=alert_counts.get(group.id, 0),
                    )
                    if not with_alert_count:
                        item.pop("open_alert_count")
                        item["has_open_alert"] = alert_counts.get(group.id, 0) > 0
                    items.append(item)
        return items

    def _resolve_group(self, *, group_id: int, user_id: UUID | None):
        """读取分组并校验用户可见范围，不可见时按不存在处理。"""

        group = self._groups.get_group(group_id)
        if group is None:
            raise NotFoundError("Token 分组不存在")
        if user_id is not None and not self._groups.group_is_available_to_user(group_id, user_id):
            raise NotFoundError("Token 分组不存在")
        return group

    def _window_meta(self) -> dict:
        """返回列表接口共用的窗口元信息。"""

        newest = newest_window(datetime.now(UTC))
        oldest = recent_windows(newest=newest, count=WINDOWS_PER_DAY)[0]
        return {
            "window_minutes": WINDOW_MINUTES,
            "latest_window_start": newest.isoformat(),
            "range_start": oldest.isoformat(),
        }


def _metric_item(
    *,
    group,
    request_type: str,
    period: str,
    window_start: datetime | None,
    bucket: MetricBucket | None,
    alert_count: int,
) -> dict:
    """构造单个「分组 × 请求类型 × 时段」的指标行。"""

    return {
        "group_id": group.id,
        "group_name": group.name,
        "request_type": request_type,
        "period": period,
        "window_start": window_start.isoformat() if window_start is not None else None,
        "sample_count": bucket.sample_count if bucket is not None else 0,
        "success_rate": bucket.success_rate if bucket is not None else None,
        "average_duration_ms": bucket.average_duration_ms if bucket is not None else None,
        "average_first_token_ms": bucket.average_first_token_ms if bucket is not None else None,
        "open_alert_count": alert_count,
    }


def _series_payload(
    *,
    request_type: str,
    mode: str,
    metric: str,
    unit: str,
    label: str,
    windows: list[datetime],
    buckets: dict[tuple[str, datetime, str], MetricBucket],
) -> dict:
    """构造一条与 x 轴等长的指标序列，缺失窗口补 ``None``。"""

    return {
        "key": f"{request_type}.{metric}",
        "request_type": request_type,
        "metric": metric,
        "name": f"{_REQUEST_TYPE_LABELS.get(request_type, request_type)} · {label}",
        "unit": unit,
        "values": [_metric_value(buckets.get((mode, window_start, request_type)), metric) for window_start in windows],
    }


def _metric_value(bucket: MetricBucket | None, metric: str):
    """读取指标派生值，窗口无数据时返回 ``None``。"""

    if bucket is None:
        return None
    return getattr(bucket, metric)


def _range_summaries(*, rows: list, request_types: list[str], modes: dict[str, str]) -> list[dict]:
    """按请求类型汇总整个查询区间的计数，每个类型只累计其当前模式的数据。"""

    totals = {request_type: MetricBucket() for request_type in request_types}
    for row in rows:
        current = totals.get(row.request_type)
        if current is not None and row.mode == modes.get(row.request_type, MONITOR_MODE_REAL):
            totals[row.request_type] = current + MetricBucket.from_snapshot(row)
    return [
        {
            "request_type": request_type,
            "sample_count": bucket.sample_count,
            "success_rate": bucket.success_rate,
            "average_duration_ms": bucket.average_duration_ms,
            "average_first_token_ms": bucket.average_first_token_ms,
        }
        for request_type, bucket in totals.items()
    ]


def _alert_item(alert, group_names: dict[int, str], channel_names: dict[UUID, str]) -> dict:
    """构造单条告警记录的管理视图投影，服务器资源告警没有分组展示名。"""

    return {
        "id": str(alert.id),
        "group_id": alert.group_id,
        "group_name": None if alert.group_id is None else group_names.get(alert.group_id, f"分组 {alert.group_id}"),
        "channel_id": None if alert.channel_id is None else str(alert.channel_id),
        "channel_name": None
        if alert.channel_id is None
        else channel_names.get(alert.channel_id, str(alert.channel_id)),
        "metric": alert.metric.value,
        "status": alert.status.value,
        "first_window_start": _isoformat(alert.first_window_start),
        "last_window_start": _isoformat(alert.last_window_start),
        "triggered_at": _isoformat(alert.triggered_at),
        "resolved_at": _isoformat(alert.resolved_at),
        "acknowledged_at": _isoformat(alert.acknowledged_at),
        "sample_count": alert.sample_count,
        "actual_value": float(alert.actual_value),
        "threshold_value": float(alert.threshold_value),
        "consecutive_hits": alert.consecutive_hits,
        "notified_at": _isoformat(alert.notified_at),
        "notification_status": alert.notification_status.value,
        "notification_error": alert.notification_error,
    }


def _isoformat(moment: datetime | None) -> str | None:
    """把可选时刻序列化为 ISO 8601 字符串。"""

    return None if moment is None else moment.isoformat()


def _resolve_metrics(*, scope: str | None, metric: str | None) -> tuple[MonitorAlertMetric, ...] | None:
    """按告警范围与指定指标推导过滤集合，两者都未给出时返回空表示不过滤。"""

    if metric is not None:
        return (MonitorAlertMetric(metric),)
    if scope == ALERT_SCOPE_SERVER:
        return RESOURCE_ALERT_METRICS
    if scope == ALERT_SCOPE_GROUP:
        return BUSINESS_ALERT_METRICS
    return None
