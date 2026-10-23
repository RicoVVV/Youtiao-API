"""用户侧监控可见范围配置的数据库访问，配置表固定只有一行。"""

from sqlmodel import Session

from app.modules.monitoring.model import MONITOR_USER_VISIBILITY_ID, MonitorUserVisibility


class MonitorUserVisibilityCrud:
    """封装用户侧监控可见范围配置的读取、创建与更新。"""

    def __init__(self, session: Session) -> None:
        """绑定调用方提供的事务会话。"""

        self._session = session

    def get(self) -> MonitorUserVisibility | None:
        """读取唯一配置行。"""

        return self._session.get(MonitorUserVisibility, MONITOR_USER_VISIBILITY_ID)

    def create(self, values: dict) -> MonitorUserVisibility:
        """创建配置行并刷新。"""

        record = MonitorUserVisibility(id=MONITOR_USER_VISIBILITY_ID, **values)
        self._session.add(record)
        self._session.flush()
        return record

    def update(self, record: MonitorUserVisibility, values: dict) -> MonitorUserVisibility:
        """按字段更新配置行。"""

        for field, value in values.items():
            setattr(record, field, value)
        self._session.add(record)
        self._session.flush()
        return record
