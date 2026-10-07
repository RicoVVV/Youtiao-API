"""告警阈值规则的数据库访问。"""

from sqlalchemy import select
from sqlmodel import Session

from app.modules.monitoring.model import MonitorAlertRule


class MonitorAlertRuleCrud:
    """封装全局默认规则与分组覆盖规则的读写。"""

    def __init__(self, session: Session) -> None:
        """绑定调用方提供的事务会话。"""

        self._session = session

    def get_global(self) -> MonitorAlertRule | None:
        """读取全局默认规则，即 ``group_id`` 为空的规则行。"""

        return self._session.scalar(select(MonitorAlertRule).where(MonitorAlertRule.group_id.is_(None)))

    def get_by_group(self, group_id: int) -> MonitorAlertRule | None:
        """读取指定分组的覆盖规则。"""

        return self._session.scalar(select(MonitorAlertRule).where(MonitorAlertRule.group_id == group_id))

    def list_rules(self) -> list[MonitorAlertRule]:
        """按全局默认在前、分组主键升序列出全部规则。"""

        return list(
            self._session.scalars(
                select(MonitorAlertRule).order_by(MonitorAlertRule.group_id.nulls_first(), MonitorAlertRule.id)
            )
        )

    def create(self, values: dict) -> MonitorAlertRule:
        """创建规则行并刷新主键。"""

        rule = MonitorAlertRule(**values)
        self._session.add(rule)
        self._session.flush()
        return rule

    def update(self, rule: MonitorAlertRule, values: dict) -> MonitorAlertRule:
        """按字段更新规则行。"""

        for field, value in values.items():
            setattr(rule, field, value)
        self._session.add(rule)
        self._session.flush()
        return rule

    def soft_delete(self, rule: MonitorAlertRule) -> None:
        """逻辑删除分组覆盖规则，使其回落到全局默认。"""

        rule.is_del = True
        self._session.add(rule)
        self._session.flush()
