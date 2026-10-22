"""渠道运行时趋势采样的数据访问。"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.modules.channels.model.runtime_sample import ChannelRuntimeSample


class ChannelRuntimeSampleCrud:
    """封装趋势采样行的写入、区间查询与超期删除。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert(
        self,
        *,
        channel_id: UUID,
        bucket_start: datetime,
        effective_weight: Decimal,
        success_rate: Decimal | None,
        average_latency_ms: int | None,
        circuit_state: str,
        active: bool,
    ) -> None:
        """按渠道与分钟桶写入采样，重复采样覆盖同一行。"""

        statement = insert(ChannelRuntimeSample).values(
            id=uuid4(),
            channel_id=channel_id,
            bucket_start=bucket_start,
            effective_weight=effective_weight,
            success_rate=success_rate,
            average_latency_ms=average_latency_ms,
            circuit_state=circuit_state,
            active=active,
            is_del=False,
        )
        self._session.execute(
            statement.on_conflict_do_update(
                index_elements=["channel_id", "bucket_start"],
                set_={
                    "effective_weight": statement.excluded.effective_weight,
                    "success_rate": statement.excluded.success_rate,
                    "average_latency_ms": statement.excluded.average_latency_ms,
                    "circuit_state": statement.excluded.circuit_state,
                    "active": statement.excluded.active,
                    "is_del": False,
                },
            )
        )

    def list_range(self, *, channel_id: UUID, start_at: datetime, end_at: datetime) -> list[ChannelRuntimeSample]:
        """按时间升序读取指定渠道的趋势采样。"""

        return list(
            self._session.scalars(
                select(ChannelRuntimeSample)
                .where(
                    ChannelRuntimeSample.channel_id == channel_id,
                    ChannelRuntimeSample.bucket_start >= start_at,
                    ChannelRuntimeSample.bucket_start <= end_at,
                )
                .order_by(ChannelRuntimeSample.bucket_start.asc())
            )
        )

    def delete_expired(self, *, before: datetime) -> int:
        """删除早于保留期的采样行，返回删除行数。"""

        result = self._session.execute(delete(ChannelRuntimeSample).where(ChannelRuntimeSample.bucket_start < before))
        return int(result.rowcount or 0)
