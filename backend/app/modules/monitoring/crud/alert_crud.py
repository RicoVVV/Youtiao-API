"""分组监控告警记录的数据库访问。"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlmodel import Session

from app.modules.monitoring.model import MonitorAlert, MonitorAlertMetric, MonitorAlertStatus

CLOSED_STATUSES = (MonitorAlertStatus.resolved, MonitorAlertStatus.acknowledged, MonitorAlertStatus.ignored)
"""已结束的状态；只有这些状态的行会被保留期清理。"""


class MonitorAlertCrud:
    """封装告警记录的活跃查询、状态写入、分页与清理。"""

    def __init__(self, session: Session) -> None:
        """绑定调用方提供的事务会话。"""

        self._session = session

    def get(self, alert_id: UUID) -> MonitorAlert | None:
        """按主键读取告警记录。"""

        return self._session.get(MonitorAlert, alert_id)

    def get_current(
        self, *, group_id: int | None, channel_id: UUID | None, metric: MonitorAlertMetric
    ) -> MonitorAlert | None:
        """读取指定评估目标最近的一条告警行，包含已人工处置与已恢复的行。

        评估只面向最近一行：它决定该目标当前是否已有告警、是否已被人工处置，
        以及本次窗口是否已经评估过。``group_id`` 为空表示服务器资源告警。
        """

        return self._session.scalar(
            select(MonitorAlert)
            .where(*self._scope_conditions(group_id, channel_id, metric))
            .order_by(MonitorAlert.last_window_start.desc(), MonitorAlert.created_at.desc(), MonitorAlert.id)
            .limit(1)
        )

    def create(self, values: dict) -> MonitorAlert:
        """创建告警行并刷新主键。"""

        alert = MonitorAlert(**values)
        self._session.add(alert)
        self._session.flush()
        return alert

    def update(self, alert: MonitorAlert, values: dict) -> MonitorAlert:
        """按字段更新告警行。"""

        for field, value in values.items():
            setattr(alert, field, value)
        self._session.add(alert)
        self._session.flush()
        return alert

    def remove(self, alert: MonitorAlert) -> None:
        """硬删除未触发过的候选告警，避免瞬时抖动留下噪声记录。"""

        self._session.delete(alert)
        self._session.flush()

    def list_page(
        self,
        *,
        page: int,
        page_size: int,
        status: MonitorAlertStatus | None,
        group_id: int | None,
        channel_id: UUID | None,
        metrics: tuple[MonitorAlertMetric, ...] | None,
        since: datetime | None,
    ) -> tuple[int, list[MonitorAlert]]:
        """按筛选条件分页读取告警记录，``metrics`` 为空表示不按指标过滤。"""

        conditions = []
        if status is not None:
            conditions.append(MonitorAlert.status == status)
        if group_id is not None:
            conditions.append(MonitorAlert.group_id == group_id)
        if channel_id is not None:
            conditions.append(MonitorAlert.channel_id == channel_id)
        if metrics is not None:
            conditions.append(MonitorAlert.metric.in_(metrics))
        if since is not None:
            conditions.append(MonitorAlert.last_window_start >= since)
        total = int(
            self._session.scalar(select(func.count()).select_from(select(MonitorAlert).where(*conditions).subquery()))
            or 0
        )
        items = list(
            self._session.scalars(
                select(MonitorAlert)
                .where(*conditions)
                .order_by(MonitorAlert.updated_at.desc(), MonitorAlert.id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        return total, items

    def count_open_by_group(self) -> dict[int, int]:
        """统计每个分组当前未恢复的告警数量，服务器资源告警不计入。"""

        rows = self._session.execute(
            select(MonitorAlert.group_id, func.count())
            .where(
                MonitorAlert.status == MonitorAlertStatus.open,
                MonitorAlert.group_id.is_not(None),
            )
            .group_by(MonitorAlert.group_id)
        ).all()
        return {int(group_id): int(count) for group_id, count in rows}

    def count_open_by_channel(self, *, group_id: int) -> dict[UUID, int]:
        """统计指定分组内每个渠道当前未恢复的告警数量。"""

        rows = self._session.execute(
            select(MonitorAlert.channel_id, func.count())
            .where(
                MonitorAlert.status == MonitorAlertStatus.open,
                MonitorAlert.group_id == group_id,
                MonitorAlert.channel_id.is_not(None),
            )
            .group_by(MonitorAlert.channel_id)
        ).all()
        return {channel_id: int(count) for channel_id, count in rows if channel_id is not None}

    def delete_expired(self, *, before: datetime) -> int:
        """硬删除已结束且超过保留期的告警，返回删除行数。"""

        result = self._session.execute(
            delete(MonitorAlert).where(
                MonitorAlert.status.in_(CLOSED_STATUSES),
                MonitorAlert.updated_at < before,
            )
        )
        return int(result.rowcount or 0)

    @staticmethod
    def _scope_conditions(group_id: int | None, channel_id: UUID | None, metric: MonitorAlertMetric):
        """构造「分组 × 渠道 × 指标」的匹配条件。

        渠道为空时按分组级告警匹配；分组为空时按服务器资源告警匹配：
        必须显式使用 ``IS NULL``，否则 SQL 中 NULL 参与等值比较恒为假。
        """

        group_condition = MonitorAlert.group_id.is_(None) if group_id is None else MonitorAlert.group_id == group_id
        channel_condition = (
            MonitorAlert.channel_id.is_(None) if channel_id is None else MonitorAlert.channel_id == channel_id
        )
        return (group_condition, channel_condition, MonitorAlert.metric == metric)
