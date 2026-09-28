"""服务器资源告警阈值配置的管理用例。"""

from decimal import Decimal

from sqlmodel import Session

from app.modules.monitoring.application.contracts import default_resource_rule_values
from app.modules.monitoring.crud.resource_rule_crud import MonitorResourceRuleCrud
from app.modules.monitoring.model import MonitorResourceRule

RESOURCE_RULE_FIELDS = (
    "enabled",
    "cpu_usage_max",
    "memory_usage_max",
    "swap_usage_max",
    "disk_usage_max",
    "consecutive_hits",
)


class MonitorResourceSettingsApplicationService:
    """维护服务器资源告警的启用开关与各项阈值。"""

    def __init__(self, session: Session) -> None:
        """绑定调用方提供的事务会话。"""

        self._session = session
        self._rules = MonitorResourceRuleCrud(session)

    def current_rule(self) -> MonitorResourceRule:
        """返回资源阈值配置，缺失时按默认阈值创建。"""

        record = self._rules.get()
        if record is not None:
            return record
        return self._rules.create(default_resource_rule_values())

    def rule_view(self) -> dict:
        """返回资源配置视图；未落库时返回默认值。"""

        record = self._rules.get()
        values = default_resource_rule_values() if record is None else _rule_field_values(record)
        return {"id": None if record is None else str(record.id), **_rule_view(values)}

    def update_rule(self, payload: dict) -> dict:
        """更新资源配置，未提供的字段保持原值，传空值表示不再评估该指标。"""

        values = {field: payload[field] for field in RESOURCE_RULE_FIELDS if field in payload}
        record = self._rules.get()
        try:
            if record is None:
                record = self._rules.create({**default_resource_rule_values(), **values})
            else:
                record = self._rules.update(record, values)
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
        return self.rule_view()


def _rule_field_values(record: MonitorResourceRule) -> dict:
    """把配置行转换为字段字典，与默认值结构保持一致。"""

    return {
        "enabled": record.enabled,
        "cpu_usage_max": record.cpu_usage_max,
        "memory_usage_max": record.memory_usage_max,
        "swap_usage_max": record.swap_usage_max,
        "disk_usage_max": record.disk_usage_max,
        "consecutive_hits": record.consecutive_hits,
    }


def _rule_view(values: dict) -> dict:
    """把字段字典投影为管理视图，阈值以浮点百分比输出。"""

    return {
        "enabled": values["enabled"],
        "cpu_usage_max": _optional_float(values["cpu_usage_max"]),
        "memory_usage_max": _optional_float(values["memory_usage_max"]),
        "swap_usage_max": _optional_float(values["swap_usage_max"]),
        "disk_usage_max": _optional_float(values["disk_usage_max"]),
        "consecutive_hits": values["consecutive_hits"],
    }


def _optional_float(value: Decimal | None) -> float | None:
    """把可选阈值转为浮点，空值表示不评估该指标。"""

    return None if value is None else float(value)
