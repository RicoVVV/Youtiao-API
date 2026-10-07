"""告警阈值规则与钉钉推送配置的管理用例。"""

from datetime import UTC, datetime

from sqlmodel import Session

from app.core.errors import NotFoundError
from app.modules.monitoring.application.contracts import (
    AlertAtTargets,
    default_global_rule_values,
    default_group_rule_values,
    default_notification_values,
)
from app.modules.monitoring.application.notification import DingTalkNotifier
from app.modules.monitoring.crud.alert_rule_crud import MonitorAlertRuleCrud
from app.modules.monitoring.crud.notification_crud import MonitorNotificationCrud
from app.modules.monitoring.model import MonitorAlertRule, MonitorNotification, NotificationScope
from app.modules.user.crud.token_group_crud import TokenGroupCrud

RULE_FIELDS = (
    "enabled",
    "success_rate_min",
    "avg_duration_ms_max",
    "avg_first_token_ms_max",
    "min_sample_count",
    "consecutive_hits",
    "at_mobiles",
    "at_all",
)

NOTIFICATION_FIELDS = (
    "notify_group_alerts",
    "notify_resource_alerts",
    "webhook_url",
    "sign_secret",
    "keyword",
    "timeout_seconds",
    "silence_minutes",
    "notify_on_resolved",
)


class MonitorSettingsApplicationService:
    """维护全局默认阈值、分组覆盖阈值与钉钉推送配置。"""

    def __init__(self, session: Session) -> None:
        """绑定调用方提供的事务会话。"""

        self._session = session
        self._rules = MonitorAlertRuleCrud(session)
        self._notifications = MonitorNotificationCrud(session)
        self._groups = TokenGroupCrud(session)

    def evaluation_rules(self) -> tuple[MonitorAlertRule, dict[int, MonitorAlertRule]]:
        """返回评估所需的全局默认规则与分组覆盖规则，缺失时补齐全局默认行。"""

        global_rule = self._get_or_create_global_rule()
        overrides = {rule.group_id: rule for rule in self._rules.list_rules() if rule.group_id is not None}
        return global_rule, overrides

    def current_notification(self) -> MonitorNotification:
        """返回推送配置，缺失时补齐默认行。"""

        return self._get_or_create_notification()

    def list_rule_views(self) -> list[dict]:
        """列出全局默认规则与全部分组覆盖规则。"""

        self._get_or_create_global_rule()
        self._session.commit()
        rules = self._rules.list_rules()
        names = self._group_names(rules)
        return [self._rule_view(rule, names) for rule in rules]

    def upsert_rule(self, payload: dict) -> dict:
        """按 ``group_id`` 新增或更新分组覆盖规则，未提供时更新全局默认规则。"""

        group_id = payload.get("group_id")
        if (
            group_id is not None
            and self._rules.get_by_group(group_id) is None
            and self._groups.get_group(group_id) is None
        ):
            raise NotFoundError("Token 分组不存在")
        values = {field: payload[field] for field in RULE_FIELDS if field in payload}
        rule = self._rules.get_global() if group_id is None else self._rules.get_by_group(group_id)
        try:
            if rule is None:
                defaults = default_global_rule_values() if group_id is None else default_group_rule_values(group_id)
                rule = self._rules.create({**defaults, **values})
            else:
                rule = self._rules.update(rule, values)
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
        return self._rule_view(rule, self._group_names([rule]))

    def delete_group_rule(self, group_id: int) -> None:
        """删除分组覆盖规则，使其回落到全局默认阈值。"""

        rule = self._rules.get_by_group(group_id)
        if rule is None:
            raise NotFoundError("分组告警规则不存在")
        try:
            self._rules.soft_delete(rule)
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise

    def notification_view(self) -> dict:
        """返回推送配置视图；未落库时返回默认值。"""

        record = self._notifications.get()
        if record is None:
            return {**default_notification_values(), "sign_secret_configured": False}
        return self._notification_view(record)

    def update_notification(self, payload: dict) -> dict:
        """更新推送配置，未提供的字段保持原值。"""

        values = {field: payload[field] for field in NOTIFICATION_FIELDS if field in payload}
        record = self._notifications.get()
        try:
            if record is None:
                record = self._notifications.create({**default_notification_values(), **values})
            else:
                record = self._notifications.update(record, values)
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
        return self._notification_view(record)

    def send_test_notification(self, scope: str) -> dict:
        """按指定告警范围发送测试通知，@ 目标取全局默认规则配置。"""

        record = self.current_notification()
        global_rule, _ = self.evaluation_rules()
        self._session.commit()
        result = DingTalkNotifier(record).send_test(
            scope=NotificationScope(scope), at=AlertAtTargets.from_rules(global_rule)
        )
        return {"status": result.status.value, "error": result.error, "sent_at": datetime.now(UTC).isoformat()}

    def _get_or_create_global_rule(self) -> MonitorAlertRule:
        """读取全局默认规则，缺失时按默认阈值创建。"""

        rule = self._rules.get_global()
        if rule is not None:
            return rule
        return self._rules.create(default_global_rule_values())

    def _get_or_create_notification(self) -> MonitorNotification:
        """读取推送配置，缺失时按默认值创建。"""

        record = self._notifications.get()
        if record is not None:
            return record
        return self._notifications.create(default_notification_values())

    def _group_names(self, rules: list[MonitorAlertRule]) -> dict[int, str]:
        """读取规则涉及的分组名称，供管理视图展示。"""

        group_ids = {rule.group_id for rule in rules if rule.group_id is not None}
        return {group.id: group.name for group in self._groups.list_groups_by_ids(group_ids)}

    @staticmethod
    def _rule_view(rule: MonitorAlertRule, names: dict[int, str]) -> dict:
        """把规则行转换为管理视图投影。"""

        return {
            "id": str(rule.id),
            "group_id": rule.group_id,
            "group_name": names.get(rule.group_id) if rule.group_id is not None else None,
            "enabled": rule.enabled,
            "success_rate_min": None if rule.success_rate_min is None else float(rule.success_rate_min),
            "avg_duration_ms_max": rule.avg_duration_ms_max,
            "avg_first_token_ms_max": rule.avg_first_token_ms_max,
            "min_sample_count": rule.min_sample_count,
            "consecutive_hits": rule.consecutive_hits,
            "at_mobiles": rule.at_mobiles,
            "at_all": rule.at_all,
        }

    @staticmethod
    def _notification_view(record: MonitorNotification) -> dict:
        """把推送配置转换为管理视图投影，密钥只返回是否已配置。"""

        return {
            "notify_group_alerts": record.notify_group_alerts,
            "notify_resource_alerts": record.notify_resource_alerts,
            "webhook_url": record.webhook_url,
            "keyword": record.keyword,
            "timeout_seconds": record.timeout_seconds,
            "silence_minutes": record.silence_minutes,
            "notify_on_resolved": record.notify_on_resolved,
            "sign_secret_configured": bool(record.sign_secret.strip()),
        }
