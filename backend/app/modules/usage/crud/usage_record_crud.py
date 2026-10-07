"""使用记录的数据访问。"""

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from app.modules.usage.model import UsageDailyStatistic, UsageRecord, UsageRecordStatus
from app.modules.user.model.user import User
from app.modules.video.model.video_task import VideoTask
from sqlalchemy import func
from sqlalchemy import select as sqlalchemy_select
from sqlalchemy.orm import selectinload
from sqlmodel import Session, select


class UsageRecordCrud:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, record: UsageRecord) -> UsageRecord:
        self._session.add(record)
        self._session.flush()
        return record

    def get_for_resource_update(self, *, resource_type: str, resource_id: UUID) -> UsageRecord | None:
        return self._session.scalar(
            sqlalchemy_select(UsageRecord)
            .where(UsageRecord.resource_type == resource_type, UsageRecord.resource_id == resource_id)
            .with_for_update()
        )

    def get_owned(self, *, usage_record_id: UUID, user_id: UUID) -> UsageRecord | None:
        return self._session.exec(
            select(UsageRecord).where(UsageRecord.id == usage_record_id, UsageRecord.user_id == user_id)
        ).first()

    def get(self, usage_record_id: UUID) -> UsageRecord | None:
        record = self._session.exec(
            select(UsageRecord).options(selectinload(UsageRecord.user)).where(UsageRecord.id == usage_record_id)
        ).first()
        self._attach_upstream_task_ids([record] if record is not None else [])
        return record

    def rebuild_daily_statistics(self, stat_date: date, start_at: datetime, end_at: datetime) -> int:
        existing = select(UsageDailyStatistic).where(UsageDailyStatistic.stat_date == stat_date)
        for item in self._session.exec(existing):
            self._session.delete(item)
        records = self._session.exec(
            select(UsageRecord).where(
                UsageRecord.created_at >= start_at,
                UsageRecord.created_at < end_at,
                UsageRecord.status.in_((UsageRecordStatus.succeeded, UsageRecordStatus.refunded)),
            )
        )
        grouped: dict[tuple, dict] = defaultdict(
            lambda: {
                "succeeded_count": 0,
                "refunded_count": 0,
                "settled_amount": Decimal("0"),
                "total_duration_ms": 0,
                "total_tokens": 0,
            }
        )
        for record in records:
            key = (
                record.user_id,
                record.access_token_id,
                record.token_display_name,
                record.request_type,
                record.model_id,
                record.model_name,
                record.channel_id,
                record.channel_name,
                record.provider_name,
            )
            item = grouped[key]
            if record.status == UsageRecordStatus.succeeded:
                item["succeeded_count"] += 1
                item["settled_amount"] += record.amount
                item["total_duration_ms"] += record.duration_ms or 0
                item["total_tokens"] += (record.prompt_tokens or 0) + (record.completion_tokens or 0)
            else:
                item["refunded_count"] += 1
        for key, values in grouped.items():
            self._session.add(
                UsageDailyStatistic(
                    stat_date=stat_date,
                    user_id=key[0],
                    access_token_id=key[1],
                    token_display_name=key[2],
                    request_type=key[3],
                    model_id=key[4],
                    model_name=key[5],
                    channel_id=key[6],
                    channel_name=key[7],
                    provider_name=key[8],
                    **values,
                )
            )
        self._session.flush()
        return len(grouped)

    def list_statistics_records(self, *, start_at: datetime, end_at: datetime, filters: dict) -> list[UsageRecord]:
        statement = select(UsageRecord).where(UsageRecord.created_at >= start_at, UsageRecord.created_at < end_at)
        return list(self._session.exec(self._apply_statistic_filters(statement, UsageRecord, filters)))

    def list_daily_statistics(self, *, start_date: date, end_date: date, filters: dict) -> list[UsageDailyStatistic]:
        statement = select(UsageDailyStatistic).where(
            UsageDailyStatistic.stat_date >= start_date, UsageDailyStatistic.stat_date < end_date
        )
        return list(self._session.exec(self._apply_statistic_filters(statement, UsageDailyStatistic, filters)))

    @staticmethod
    def _apply_statistic_filters(statement, model, filters: dict):
        for name in ("user_id", "access_token_id", "request_type", "model_id", "channel_id", "provider_name"):
            value = filters.get(name)
            if value is not None:
                statement = statement.where(getattr(model, name) == value)
        return statement

    def list_owned(
        self,
        *,
        user_id: UUID,
        page: int,
        page_size: int,
        request_type: str | None,
        model_name: str | None,
        token_display_name: str | None,
        status: str | None,
    ) -> tuple[int, list[UsageRecord]]:
        statement = select(UsageRecord).where(UsageRecord.user_id == user_id)
        return self._list(statement, page, page_size, request_type, model_name, token_display_name, status, None)

    def list_admin(
        self,
        *,
        page: int,
        page_size: int,
        user_id: UUID | None,
        request_type: str | None,
        model_name: str | None,
        token_display_name: str | None,
        status: str | None,
        channel_id: UUID | None,
        provider_name: str | None,
        username: str | None,
    ) -> tuple[int, list[UsageRecord]]:
        statement = select(UsageRecord).options(selectinload(UsageRecord.user))
        if user_id is not None:
            statement = statement.where(UsageRecord.user_id == user_id)
        if provider_name is not None:
            statement = statement.where(UsageRecord.provider_name == provider_name)
        if username is not None:
            statement = statement.where(
                UsageRecord.user_id.in_(select(User.id).where(User.username.like(f"%{username}%")))
            )
        total, items = self._list(
            statement, page, page_size, request_type, model_name, token_display_name, status, channel_id
        )
        self._attach_upstream_task_ids(items)
        return total, items

    def _attach_upstream_task_ids(self, records: list[UsageRecord]) -> None:
        task_ids = [
            record.resource_id
            for record in records
            if record.resource_type == "video_task" and record.resource_id is not None
        ]
        if not task_ids:
            return
        upstream_task_ids = dict(
            self._session.exec(select(VideoTask.id, VideoTask.upstream_task_id).where(VideoTask.id.in_(task_ids))).all()
        )
        for record in records:
            if record.resource_type == "video_task" and record.resource_id is not None:
                record.__dict__["_upstream_task_id"] = upstream_task_ids.get(record.resource_id)

    def _list(
        self,
        statement,
        page: int,
        page_size: int,
        request_type: str | None,
        model_name: str | None,
        token_display_name: str | None,
        status: str | None,
        channel_id: UUID | None,
    ) -> tuple[int, list[UsageRecord]]:
        if request_type is not None:
            statement = statement.where(UsageRecord.request_type == request_type)
        if model_name is not None:
            statement = statement.where(UsageRecord.model_name == model_name)
        if token_display_name is not None:
            statement = statement.where(UsageRecord.token_display_name == token_display_name)
        if status is not None:
            statement = statement.where(UsageRecord.status == status)
        if channel_id is not None:
            statement = statement.where(UsageRecord.channel_id == channel_id)
        total = int(self._session.scalar(sqlalchemy_select(func.count()).select_from(statement.subquery())) or 0)
        items = list(
            self._session.exec(
                statement.order_by(UsageRecord.created_at.desc(), UsageRecord.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        return total, items
