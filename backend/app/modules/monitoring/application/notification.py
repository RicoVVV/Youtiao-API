"""钉钉自定义机器人推送。

本模块只负责按钉钉协议构造并发送消息：加签参数、markdown 报文、@ 目标与返回码校验；
推送失败只返回结果，不抛出业务异常，避免影响告警状态流转。
"""

import base64
import hashlib
import hmac
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from urllib.parse import quote_plus, urlparse
from zoneinfo import ZoneInfo

from app.infrastructure.http.client import get_http_client
from app.modules.monitoring.application.contracts import AlertAtTargets
from app.modules.monitoring.application.window import SERVER_WINDOW_MINUTES, WINDOW_MINUTES
from app.modules.monitoring.model import (
    MonitorAlert,
    MonitorAlertMetric,
    MonitorAlertNotificationStatus,
    MonitorNotification,
    NotificationScope,
)

logger = logging.getLogger(__name__)

SHANGHAI = ZoneInfo("Asia/Shanghai")
"""推送文案中的时间统一按东八区展示。"""

RETRY_DELAYS = (1.0, 2.0)
"""首次发送失败后的重试间隔秒数，共重试两次。"""

SERVER_TARGET_NAME = "服务器"
"""服务器资源告警在推送文案中的目标名称。"""

SERVER_SCOPE = "服务器监控"
"""服务器资源告警的报文范围标题。"""

GROUP_SCOPE = "分组监控"
"""分组业务告警的报文范围标题。"""

_MAX_ERROR_LENGTH = 500

_METRIC_LABELS = {
    MonitorAlertMetric.success_rate: "成功率",
    MonitorAlertMetric.average_duration_ms: "平均耗时",
    MonitorAlertMetric.average_first_token_ms: "平均首 token 耗时",
    MonitorAlertMetric.cpu_usage: "CPU 使用率",
    MonitorAlertMetric.memory_usage: "内存使用率",
    MonitorAlertMetric.swap_usage: "交换分区使用率",
    MonitorAlertMetric.disk_usage: "磁盘使用率",
}

_PERCENT_METRICS = frozenset(
    {
        MonitorAlertMetric.cpu_usage,
        MonitorAlertMetric.memory_usage,
        MonitorAlertMetric.swap_usage,
        MonitorAlertMetric.disk_usage,
    }
)
"""取值本身即百分比（0~100）的指标，成功率按 0~1 单独处理。"""


@dataclass(frozen=True, slots=True)
class NotificationResult:
    """一次推送的结果。"""

    status: MonitorAlertNotificationStatus
    error: str | None = None


class DingTalkNotifier:
    """按钉钉自定义机器人协议推送告警消息。"""

    def __init__(self, config: MonitorNotification) -> None:
        """接收当前推送配置快照。"""

        self._config = config

    def send_alert(
        self,
        *,
        alert: MonitorAlert,
        target_label: str,
        channel_name: str | None,
        resolved: bool,
        at: AlertAtTargets,
    ) -> NotificationResult:
        """推送一条告警或恢复通知；恢复通知不 @ 任何人。"""

        scope = NotificationScope.server if alert.group_id is None else NotificationScope.group
        if not self._enabled_for(scope):
            return NotificationResult(MonitorAlertNotificationStatus.skipped, "推送未启用")
        return self._post(
            _build_alert_payload(
                keyword=self._config.keyword,
                alert=alert,
                target_label=target_label,
                channel_name=channel_name,
                resolved=resolved,
                at=at,
            )
        )

    def send_test(self, *, scope: NotificationScope, at: AlertAtTargets) -> NotificationResult:
        """按指定告警范围发送一条测试通知，用于管理员校验机器人配置。"""

        if not self._enabled_for(scope):
            return NotificationResult(MonitorAlertNotificationStatus.skipped, "推送未启用")
        return self._post(_build_test_payload(keyword=self._config.keyword, at=at))

    def _enabled_for(self, scope: NotificationScope) -> bool:
        """推送是否可用：对应范围的开关打开且配置了 webhook 地址。"""

        if not self._config.webhook_url.strip():
            return False
        if scope == NotificationScope.server:
            return bool(self._config.notify_resource_alerts)
        return bool(self._config.notify_group_alerts)

    def _post(self, payload: dict) -> NotificationResult:
        """发送报文并在失败时重试，返回最终结果。"""

        base_url = self._config.webhook_url.strip()
        client = get_http_client()
        last_error = "推送失败"
        for attempt in range(len(RETRY_DELAYS) + 1):
            if attempt:
                time.sleep(RETRY_DELAYS[attempt - 1])
            try:
                response = client.post(
                    _signed_url(base_url, self._config.sign_secret),
                    json=payload,
                    timeout=self._config.timeout_seconds,
                )
                body = response.json() if response.content else {}
            except Exception as exc:
                last_error = _safe_error(exc)
                continue
            errcode = body.get("errcode")
            if errcode in (0, "0"):
                return NotificationResult(MonitorAlertNotificationStatus.sent, None)
            last_error = _safe_error(f"钉钉返回错误 {errcode}：{body.get('errmsg') or ''}")
        logger.warning("钉钉告警推送失败：%s", last_error)
        return NotificationResult(MonitorAlertNotificationStatus.failed, last_error)


def _signed_url(webhook_url: str, sign_secret: str) -> str:
    """按钉钉加签规则拼接 timestamp 与 sign 查询参数。"""

    secret = sign_secret.strip()
    if not secret:
        return webhook_url
    timestamp = str(round(time.time() * 1000))
    digest = hmac.new(
        secret.encode("utf-8"),
        f"{timestamp}\n{secret}".encode(),
        digestmod=hashlib.sha256,
    ).digest()
    sign = quote_plus(base64.b64encode(digest).decode())
    separator = "&" if urlparse(webhook_url).query else "?"
    return f"{webhook_url}{separator}timestamp={timestamp}&sign={sign}"


def _build_alert_payload(
    *,
    keyword: str,
    alert: MonitorAlert,
    target_label: str,
    channel_name: str | None,
    resolved: bool,
    at: AlertAtTargets,
) -> dict:
    """构造告警 markdown 报文。

    服务器资源告警没有分组与渠道维度，只展示目标名称与连续命中次数；
    分组业务告警的表现形式保持不变。恢复通知不 @ 任何人。
    """

    prefix = _keyword_prefix(keyword)
    metric_label = _METRIC_LABELS.get(alert.metric, alert.metric.value)
    state = "恢复" if resolved else "告警"
    is_resource = alert.group_id is None
    scope = SERVER_SCOPE if is_resource else GROUP_SCOPE
    if is_resource:
        lines = [f"#### {prefix}{scope}{state}", f"- 目标：{target_label}"]
    else:
        lines = [
            f"#### {prefix}{scope}{state}",
            f"- 分组：{target_label}",
            f"- 渠道：{channel_name or '-'}",
        ]
    lines.append(f"- 指标：{metric_label}")
    lines.append(
        f"- 当前值：{_format_metric(alert.metric, alert.actual_value)}"
        f" / 阈值：{_format_metric(alert.metric, alert.threshold_value)}"
    )
    if is_resource:
        lines.append(f"- 连续命中：{alert.consecutive_hits}")
        lines.append(f"- 窗口：{_format_window(alert.last_window_start, minutes=SERVER_WINDOW_MINUTES)}")
    else:
        lines.append(f"- 样本数：{alert.sample_count} / 连续命中：{alert.consecutive_hits}")
        lines.append(f"- 窗口：{_format_window(alert.last_window_start, minutes=WINDOW_MINUTES)}")
    if resolved and alert.resolved_at is not None:
        lines.append(f"- 恢复时间：{_format_time(alert.resolved_at)}")
    payload = {
        "msgtype": "markdown",
        "markdown": {
            "title": f"{prefix}[{scope}] {target_label} · {metric_label}{state}",
            "text": "\n".join(lines) + "\n",
        },
    }
    if resolved:
        return payload
    return _with_mention(payload, at)


def _build_test_payload(*, keyword: str, at: AlertAtTargets) -> dict:
    """构造测试通知报文，推送配置由分组告警与资源告警共用。"""

    prefix = _keyword_prefix(keyword)
    return _with_mention(
        {
            "msgtype": "markdown",
            "markdown": {
                "title": f"{prefix}[监控] 测试通知",
                "text": f"#### {prefix}监控测试通知\n告警推送配置可用。\n",
            },
        },
        at,
    )


def _with_mention(payload: dict, at: AlertAtTargets) -> dict:
    """把 @ 目标写入 markdown 正文与 ``at`` 对象；没有 @ 目标时原样返回。

    钉钉要求 markdown 正文中出现 ``@手机号`` 且 ``at`` 对象带上同一手机号才会真正提醒。
    """

    if at.empty:
        return payload
    text = payload["markdown"]["text"]
    payload["markdown"]["text"] = f"{text}\n{at.mention_text()}\n"
    payload["at"] = at.payload()
    return payload


def _keyword_prefix(keyword: str) -> str:
    """把机器人自定义关键词渲染为标题前缀，兼容关键词安全设置。"""

    normalized = keyword.strip()
    return f"[{normalized}]" if normalized else ""


def _format_metric(metric: MonitorAlertMetric, value: Decimal) -> str:
    """按指标语义格式化数值：成功率按 0~1 换算，资源使用率本身即百分比。"""

    if metric == MonitorAlertMetric.success_rate:
        return f"{value * 100:.2f}%"
    if metric in _PERCENT_METRICS:
        return f"{value:.2f}%"
    return f"{int(value)} ms"


def _format_window(window_start: datetime, *, minutes: int) -> str:
    """把窗口起点格式化为本地时间的起止表达。"""

    local_start = window_start.astimezone(SHANGHAI)
    local_end = (window_start + timedelta(minutes=minutes)).astimezone(SHANGHAI)
    return f"{local_start:%Y-%m-%d %H:%M} ~ {local_end:%H:%M}"


def _format_time(moment: datetime) -> str:
    """把时刻格式化为本地时间字符串。"""

    return f"{moment.astimezone(SHANGHAI):%Y-%m-%d %H:%M:%S}"


def _safe_error(error: object) -> str:
    """截断错误描述，避免把超长响应或敏感内容写入告警记录。"""

    text = str(error).strip().replace("\n", " ")
    return text[:_MAX_ERROR_LENGTH] if text else "推送失败"
