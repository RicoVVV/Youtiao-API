"""分组文本嗅探结果的数据库访问。"""

from datetime import datetime

from sqlalchemy import delete
from sqlmodel import Session

from app.modules.monitoring.model import GroupProbeResult


class GroupProbeResultCrud:
    """封装嗅探结果写入与清理。"""

    def __init__(self, session: Session) -> None:
        """绑定调用方提供的事务会话。"""

        self._session = session

    def create(self, record: GroupProbeResult) -> GroupProbeResult:
        """写入一条嗅探结果并刷新。"""

        self._session.add(record)
        self._session.flush()
        return record

    def delete_expired(self, *, before: datetime) -> int:
        """硬删除早于指定完成时间的嗅探结果，返回删除行数。"""

        result = self._session.execute(delete(GroupProbeResult).where(GroupProbeResult.completed_at < before))
        return int(result.rowcount or 0)
