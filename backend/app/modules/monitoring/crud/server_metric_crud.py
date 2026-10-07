"""服务器资源快照的数据库访问。"""

from datetime import datetime

from sqlalchemy import delete, func, select
from sqlmodel import Session

from app.modules.monitoring.model import ServerMetricSnapshot


class ServerMetricCrud:
    """封装服务器资源快照的写入、读取与超期清理。"""

    def __init__(self, session: Session) -> None:
        """绑定调用方提供的事务会话。"""

        self._session = session

    def get_by_window(self, *, window_start: datetime) -> ServerMetricSnapshot | None:
        """按窗口起点读取快照，用于判断该窗口是否已采集。"""

        return self._session.scalar(
            select(ServerMetricSnapshot).where(ServerMetricSnapshot.window_start == window_start)
        )

    def get_latest(self) -> ServerMetricSnapshot | None:
        """读取最新一行快照。"""

        return self._session.scalar(
            select(ServerMetricSnapshot).order_by(ServerMetricSnapshot.window_start.desc()).limit(1)
        )

    def get_previous(self, *, window_start: datetime) -> ServerMetricSnapshot | None:
        """读取早于指定窗口的最近一行快照，作为差值计算的基准。"""

        return self._session.scalar(
            select(ServerMetricSnapshot)
            .where(ServerMetricSnapshot.window_start < window_start)
            .order_by(ServerMetricSnapshot.window_start.desc())
            .limit(1)
        )

    def replace_window(self, *, window_start: datetime, values: dict) -> ServerMetricSnapshot:
        """按窗口整体重写快照，重复执行结果一致。"""

        self._session.execute(delete(ServerMetricSnapshot).where(ServerMetricSnapshot.window_start == window_start))
        snapshot = ServerMetricSnapshot(**values)
        self._session.add(snapshot)
        self._session.flush()
        return snapshot

    def list_range(self, *, start_at: datetime, end_at: datetime) -> list[ServerMetricSnapshot]:
        """按窗口升序读取区间内的快照。"""

        return list(
            self._session.scalars(
                select(ServerMetricSnapshot)
                .where(
                    ServerMetricSnapshot.window_start >= start_at,
                    ServerMetricSnapshot.window_start <= end_at,
                )
                .order_by(ServerMetricSnapshot.window_start)
            )
        )

    def count(self) -> int:
        """统计快照总行数，用于确认采集是否已经产出数据。"""

        return int(self._session.scalar(select(func.count()).select_from(ServerMetricSnapshot)) or 0)

    def delete_expired(self, *, before: datetime) -> int:
        """硬删除早于指定窗口起点的快照，返回删除行数。"""

        result = self._session.execute(delete(ServerMetricSnapshot).where(ServerMetricSnapshot.window_start < before))
        return int(result.rowcount or 0)
