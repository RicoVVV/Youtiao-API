"""告警推送配置的数据库访问，配置表固定只有一行。"""

from sqlmodel import Session

from app.modules.monitoring.model import MONITOR_NOTIFICATION_ID, MonitorNotification


class MonitorNotificationCrud:
    """封装钉钉推送配置的读取、创建与更新。"""

    def __init__(self, session: Session) -> None:
        """绑定调用方提供的事务会话。"""

        self._session = session

    def get(self) -> MonitorNotification | None:
        """读取唯一配置行。"""

        return self._session.get(MonitorNotification, MONITOR_NOTIFICATION_ID)

    def create(self, values: dict) -> MonitorNotification:
        """创建配置行并刷新。"""

        record = MonitorNotification(id=MONITOR_NOTIFICATION_ID, **values)
        self._session.add(record)
        self._session.flush()
        return record

    def update(self, record: MonitorNotification, values: dict) -> MonitorNotification:
        """按字段更新配置行。"""

        for field, value in values.items():
            setattr(record, field, value)
        self._session.add(record)
        self._session.flush()
        return record
