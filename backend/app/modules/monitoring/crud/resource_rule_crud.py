"""服务器资源告警阈值配置的数据库访问，配置表固定只有一行。"""

from sqlmodel import Session

from app.modules.monitoring.model import MONITOR_RESOURCE_RULE_ID, MonitorResourceRule


class MonitorResourceRuleCrud:
    """封装资源告警阈值配置的读取、创建与更新。"""

    def __init__(self, session: Session) -> None:
        """绑定调用方提供的事务会话。"""

        self._session = session

    def get(self) -> MonitorResourceRule | None:
        """读取唯一配置行。"""

        return self._session.get(MonitorResourceRule, MONITOR_RESOURCE_RULE_ID)

    def create(self, values: dict) -> MonitorResourceRule:
        """创建配置行并刷新。"""

        record = MonitorResourceRule(id=MONITOR_RESOURCE_RULE_ID, **values)
        self._session.add(record)
        self._session.flush()
        return record

    def update(self, record: MonitorResourceRule, values: dict) -> MonitorResourceRule:
        """按字段更新配置行。"""

        for field, value in values.items():
            setattr(record, field, value)
        self._session.add(record)
        self._session.flush()
        return record
