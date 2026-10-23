"""分组监控数据模式配置的数据库访问，配置表固定只有一行。"""

from sqlmodel import Session

from app.modules.monitoring.model import MONITOR_TRAFFIC_SETTING_ID, MonitorTrafficSetting


class MonitorTrafficSettingCrud:
    """封装监控数据模式配置的读取、创建与更新。"""

    def __init__(self, session: Session) -> None:
        """绑定调用方提供的事务会话。"""

        self._session = session

    def get(self) -> MonitorTrafficSetting | None:
        """读取唯一配置行。"""

        return self._session.get(MonitorTrafficSetting, MONITOR_TRAFFIC_SETTING_ID)

    def create(self, values: dict) -> MonitorTrafficSetting:
        """创建配置行并刷新。"""

        record = MonitorTrafficSetting(id=MONITOR_TRAFFIC_SETTING_ID, **values)
        self._session.add(record)
        self._session.flush()
        return record

    def update(self, record: MonitorTrafficSetting, values: dict) -> MonitorTrafficSetting:
        """按字段更新配置行。"""

        for field, value in values.items():
            setattr(record, field, value)
        self._session.add(record)
        self._session.flush()
        return record

    def refresh(self, record: MonitorTrafficSetting) -> None:
        """刷新配置行的数据库状态。"""

        self._session.refresh(record)
