"""分组级监控快照的数据库访问。

本模块直接读取 ``usage_records`` 归属窗口并聚合计数，只关心原始计数，
成功率与平均值等派生指标由 ``MetricBucket`` 值对象提供。
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import ColumnElement, and_, case, delete, func, select
from sqlmodel import Session

from app.modules.monitoring.model import GroupMetricSnapshot
from app.modules.monitoring.model.metric_bucket import MetricBucket
from app.modules.usage.model import UsageRecord, UsageRecordStatus

TRACKED_REQUEST_TYPES = ("text", "image", "video")
"""纳入分组监控的请求类型；渠道测试等其它类型不参与统计。"""

_TERMINAL_STATUSES = (UsageRecordStatus.succeeded, UsageRecordStatus.failed, UsageRecordStatus.refunded)
"""参与统计的终态；``reserved`` 表示尚未完成，不计入任何窗口。"""

_SUCCEEDED = UsageRecord.status == UsageRecordStatus.succeeded
_FIRST_TOKEN_RECORDED = and_(_SUCCEEDED, UsageRecord.first_token_duration_ms.is_not(None))


class SnapshotCrud:
    """封装分组级监控快照的聚合查询、窗口重写与清理。"""

    def __init__(self, session: Session) -> None:
        """绑定调用方提供的事务会话。"""

        self._session = session

    def aggregate_by_group(self, *, start_at: datetime, end_at: datetime) -> dict[tuple[int, str], MetricBucket]:
        """按「分组 × 请求类型」聚合窗口内的终态请求计数。"""

        statement = self._aggregate_statement(
            start_at=start_at,
            end_at=end_at,
            dimension_column=UsageRecord.request_type,
        )
        return {
            (row.token_group_id, row.dimension): _to_bucket(row)
            for row in self._session.execute(statement).all()
            if row.token_group_id is not None
        }

    def aggregate_by_channel(
        self, *, start_at: datetime, end_at: datetime
    ) -> dict[tuple[int, UUID, str], MetricBucket]:
        """按「分组 × 渠道 × 请求类型」聚合窗口内的终态请求计数，仅供告警定位使用。"""

        statement = self._aggregate_statement(
            start_at=start_at,
            end_at=end_at,
            dimension_column=UsageRecord.request_type,
            extra_column=UsageRecord.channel_id,
        ).where(UsageRecord.channel_id.is_not(None))
        return {
            (row.token_group_id, row.channel_id, row.dimension): _to_bucket(row)
            for row in self._session.execute(statement).all()
            if row.token_group_id is not None and row.channel_id is not None
        }

    def replace_window(self, *, window_start: datetime, buckets: dict[tuple[int, str], MetricBucket]) -> int:
        """按窗口整体重写分组级快照，重复执行结果一致。"""

        self._session.execute(delete(GroupMetricSnapshot).where(GroupMetricSnapshot.window_start == window_start))
        for (group_id, request_type), bucket in buckets.items():
            self._session.add(
                GroupMetricSnapshot(
                    window_start=window_start,
                    token_group_id=group_id,
                    request_type=request_type,
                    succeeded_count=bucket.succeeded_count,
                    failed_count=bucket.failed_count,
                    refunded_count=bucket.refunded_count,
                    total_duration_ms=bucket.total_duration_ms,
                    first_token_sum_ms=bucket.first_token_sum_ms,
                    first_token_count=bucket.first_token_count,
                )
            )
        self._session.flush()
        return len(buckets)

    def window_has_rows(self, *, window_start: datetime) -> bool:
        """判断窗口是否已有快照，用于跳过已聚合窗口。"""

        return (
            self._session.scalar(select(GroupMetricSnapshot.id).where(GroupMetricSnapshot.window_start == window_start))
            is not None
        )

    def list_window(self, *, window_start: datetime) -> list[GroupMetricSnapshot]:
        """读取单个窗口的全部分组快照。"""

        return list(
            self._session.scalars(select(GroupMetricSnapshot).where(GroupMetricSnapshot.window_start == window_start))
        )

    def list_range(
        self, *, start_at: datetime, end_at: datetime, group_ids: list[int] | None = None
    ) -> list[GroupMetricSnapshot]:
        """读取区间内的分组快照，可按分组过滤，按窗口与分组稳定排序。"""

        statement = select(GroupMetricSnapshot).where(
            GroupMetricSnapshot.window_start >= start_at,
            GroupMetricSnapshot.window_start <= end_at,
        )
        if group_ids is not None:
            statement = statement.where(GroupMetricSnapshot.token_group_id.in_(group_ids))
        return list(
            self._session.scalars(
                statement.order_by(GroupMetricSnapshot.window_start, GroupMetricSnapshot.token_group_id)
            )
        )

    def delete_expired(self, *, before: datetime) -> int:
        """硬删除早于指定窗口起点的快照，返回删除行数。"""

        result = self._session.execute(delete(GroupMetricSnapshot).where(GroupMetricSnapshot.window_start < before))
        return int(result.rowcount or 0)

    def _aggregate_statement(
        self,
        *,
        start_at: datetime,
        end_at: datetime,
        dimension_column: ColumnElement,
        extra_column: ColumnElement | None = None,
    ):
        """构造窗口内终态请求的计数聚合语句。

        ``dimension_column`` 为请求类型列；传入 ``extra_column`` 时额外按该列分组，
        用于构造「分组 × 渠道 × 请求类型」的运维视角计数。

        分组列与选择列分开构造：选择列给维度列起 ``dimension`` 别名供行映射使用，
        分组列只用原始维度列，避免把聚合表达式写进 ``GROUP BY``。
        """

        group_columns = [UsageRecord.token_group_id]
        select_columns = [UsageRecord.token_group_id]
        if extra_column is not None:
            group_columns.append(extra_column)
            select_columns.append(extra_column)
        group_columns.append(dimension_column)
        select_columns.append(dimension_column.label("dimension"))
        return (
            select(
                *select_columns,
                _count_of(_SUCCEEDED).label("succeeded_count"),
                _count_of(UsageRecord.status == UsageRecordStatus.failed).label("failed_count"),
                _count_of(UsageRecord.status == UsageRecordStatus.refunded).label("refunded_count"),
                _sum_of(_SUCCEEDED, UsageRecord.duration_ms).label("total_duration_ms"),
                _sum_of(_FIRST_TOKEN_RECORDED, UsageRecord.first_token_duration_ms).label("first_token_sum_ms"),
                _count_of(_FIRST_TOKEN_RECORDED).label("first_token_count"),
            )
            .where(
                UsageRecord.completed_at >= start_at,
                UsageRecord.completed_at < end_at,
                UsageRecord.status.in_(_TERMINAL_STATUSES),
                UsageRecord.token_group_id.is_not(None),
                UsageRecord.request_type.in_(TRACKED_REQUEST_TYPES),
            )
            .group_by(*group_columns)
        )


def _count_of(condition: ColumnElement) -> ColumnElement:
    """统计满足条件的行数，条件不满足时计 0。"""

    return func.coalesce(func.sum(case((condition, 1), else_=0)), 0)


def _sum_of(condition: ColumnElement, value_column: ColumnElement) -> ColumnElement:
    """汇总满足条件的数值列，条件不满足或值为空时计 0。"""

    return func.coalesce(func.sum(case((condition, value_column), else_=None)), 0)


def _to_bucket(row) -> MetricBucket:
    """把聚合结果行转换为指标值对象。"""

    return MetricBucket(
        succeeded_count=int(row.succeeded_count or 0),
        failed_count=int(row.failed_count or 0),
        refunded_count=int(row.refunded_count or 0),
        total_duration_ms=int(row.total_duration_ms or 0),
        first_token_sum_ms=int(row.first_token_sum_ms or 0),
        first_token_count=int(row.first_token_count or 0),
    )
