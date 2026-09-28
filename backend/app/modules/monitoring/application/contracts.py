"""分组监控应用层的共享契约与默认值。"""

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from app.modules.monitoring.model import MonitorAlertRule
from app.modules.monitoring.model.metric_bucket import MetricBucket

DEFAULT_SUCCESS_RATE_MIN = Decimal("0.9000")
DEFAULT_AVERAGE_DURATION_MS_MAX = 30000
DEFAULT_AVERAGE_FIRST_TOKEN_MS_MAX = 5000
DEFAULT_MIN_SAMPLE_COUNT = 20
DEFAULT_CONSECUTIVE_HITS = 2

DEFAULT_CPU_USAGE_MAX = Decimal("90.000")
DEFAULT_MEMORY_USAGE_MAX = Decimal("90.000")
DEFAULT_SWAP_USAGE_MAX = Decimal("80.000")
DEFAULT_DISK_USAGE_MAX = Decimal("85.000")
DEFAULT_RESOURCE_CONSECUTIVE_HITS = 3
"""资源告警默认阈值按百分比给出；连续命中按 1 分钟窗口计，默认连续 3 分钟超阈才触发。"""


def default_global_rule_values() -> dict:
    """构造全局默认告警规则的初始字段值。"""

    return {
        "group_id": None,
        "enabled": True,
        "success_rate_min": DEFAULT_SUCCESS_RATE_MIN,
        "avg_duration_ms_max": DEFAULT_AVERAGE_DURATION_MS_MAX,
        "avg_first_token_ms_max": DEFAULT_AVERAGE_FIRST_TOKEN_MS_MAX,
        "min_sample_count": DEFAULT_MIN_SAMPLE_COUNT,
        "consecutive_hits": DEFAULT_CONSECUTIVE_HITS,
        "at_mobiles": "",
        "at_all": False,
    }


def default_group_rule_values(group_id: int) -> dict:
    """构造分组覆盖规则的初始字段值，默认沿用全局阈值。"""

    return {**default_global_rule_values(), "group_id": group_id}


def default_resource_rule_values() -> dict:
    """构造服务器资源告警规则的初始字段值。"""

    return {
        "enabled": True,
        "cpu_usage_max": DEFAULT_CPU_USAGE_MAX,
        "memory_usage_max": DEFAULT_MEMORY_USAGE_MAX,
        "swap_usage_max": DEFAULT_SWAP_USAGE_MAX,
        "disk_usage_max": DEFAULT_DISK_USAGE_MAX,
        "consecutive_hits": DEFAULT_RESOURCE_CONSECUTIVE_HITS,
    }


def default_notification_values() -> dict:
    """构造钉钉推送配置的初始字段值。"""

    return {
        "notify_group_alerts": False,
        "notify_resource_alerts": False,
        "webhook_url": "",
        "sign_secret": "",
        "keyword": "",
        "timeout_seconds": 10,
        "silence_minutes": 30,
        "notify_on_resolved": False,
    }


@dataclass(frozen=True, slots=True)
class AlertThresholds:
    """一次评估使用的阈值快照，字段为空表示不评估对应指标。"""

    min_sample_count: int
    consecutive_hits: int
    success_rate_min: Decimal | None
    average_duration_ms_max: int | None
    average_first_token_ms_max: int | None

    @classmethod
    def from_rule(cls, rule: MonitorAlertRule) -> "AlertThresholds":
        """由规则行派生阈值快照。"""

        return cls(
            min_sample_count=rule.min_sample_count,
            consecutive_hits=rule.consecutive_hits,
            success_rate_min=rule.success_rate_min,
            average_duration_ms_max=rule.avg_duration_ms_max,
            average_first_token_ms_max=rule.avg_first_token_ms_max,
        )


@dataclass(frozen=True, slots=True)
class AlertEvaluationTarget:
    """一个被评估的统计目标及其窗口计数。"""

    group_id: int
    channel_id: UUID | None
    request_type: str
    bucket: MetricBucket


def parse_mobiles(raw: str) -> tuple[str, ...]:
    """把逗号分隔的手机号串解析为去重后的元组。"""

    return tuple(dict.fromkeys(part.strip() for part in raw.split(",") if part.strip()))


@dataclass(frozen=True, slots=True)
class AlertAtTargets:
    """一次推送的 @ 目标快照，手机号与 ``at_all`` 均为空表示不 @ 任何人。"""

    mobiles: tuple[str, ...] = ()
    at_all: bool = False

    @property
    def empty(self) -> bool:
        """没有任何 @ 目标。"""

        return not self.mobiles and not self.at_all

    def mention_text(self) -> str:
        """钉钉 markdown 正文中的 @ 文本；正文不出现 @ 文本时不会真正提醒。"""

        parts = [f"@{mobile}" for mobile in self.mobiles]
        if self.at_all:
            parts.append("@所有人")
        return " ".join(parts)

    def payload(self) -> dict:
        """构造钉钉 ``at`` 对象。"""

        return {"atMobiles": list(self.mobiles), "isAtAll": self.at_all}

    @classmethod
    def from_rules(cls, rule: MonitorAlertRule, *, fallback: MonitorAlertRule | None = None) -> "AlertAtTargets":
        """由规则行派生 @ 目标；未配置手机号或未开启 @所有人时沿用 ``fallback``（全局规则行）。"""

        fallback_mobiles = fallback.at_mobiles if fallback is not None else ""
        fallback_at_all = fallback.at_all if fallback is not None else False
        return cls(
            mobiles=parse_mobiles(rule.at_mobiles.strip() or fallback_mobiles.strip()),
            at_all=rule.at_all or fallback_at_all,
        )
