from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.core.errors import ValidationError
from app.modules.usage.crud.usage_record_crud import UsageRecordCrud
from app.modules.usage.model import UsageRecordStatus
from sqlmodel import Session

SHANGHAI = ZoneInfo("Asia/Shanghai")
REALTIME_DAYS = 31


class UsageStatisticsValidationError(ValidationError):
    pass


class UsageStatisticsApplicationService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._crud = UsageRecordCrud(session)

    def rebuild_daily_statistics(self, stat_date: date) -> int:
        start_at, end_at = self._day_bounds(stat_date)
        return self._crud.rebuild_daily_statistics(stat_date, start_at, end_at)

    def rebuild_recent_daily_statistics(self, days: int = 32) -> int:
        today = datetime.now(SHANGHAI).date()
        total = 0
        for offset in range(days):
            total += self.rebuild_daily_statistics(today - timedelta(days=offset))
        return total

    def overview(
        self, *, filters: dict, range_name: str | None, start_at: datetime | None, end_at: datetime | None
    ) -> dict:
        start_date, end_date = self._resolve_range(range_name=range_name, start_at=start_at, end_at=end_at)
        rows = self._collect(start_date=start_date, end_date=end_date, filters=filters)
        return self._metrics(rows)

    def trend(
        self, *, filters: dict, range_name: str | None, start_at: datetime | None, end_at: datetime | None
    ) -> list[dict]:
        start_date, end_date = self._resolve_range(range_name=range_name, start_at=start_at, end_at=end_at)
        groups: dict[date, list[dict]] = defaultdict(list)
        for row in self._collect(start_date=start_date, end_date=end_date, filters=filters):
            groups[row["stat_date"]].append(row)
        result = []
        current = start_date
        while current < end_date:
            result.append({"stat_date": current.isoformat(), **self._metrics(groups[current])})
            current += timedelta(days=1)
        return result

    def dimensions(
        self,
        *,
        dimension: str,
        filters: dict,
        range_name: str | None,
        start_at: datetime | None,
        end_at: datetime | None,
        page: int,
        page_size: int,
    ) -> tuple[int, list[dict]]:
        start_date, end_date = self._resolve_range(range_name=range_name, start_at=start_at, end_at=end_at)
        fields = {
            "user": ("user_id",),
            "model": ("model_name",),
            "channel": ("channel_id", "channel_name"),
            "provider": ("provider_name",),
            "token": ("access_token_id", "token_display_name"),
        }
        if dimension not in fields:
            raise UsageStatisticsValidationError("统计维度不合法")
        grouped: dict[tuple, list[dict]] = defaultdict(list)
        for row in self._collect(start_date=start_date, end_date=end_date, filters=filters):
            grouped[tuple(row.get(field) for field in fields[dimension])].append(row)
        items = []
        for key, rows in grouped.items():
            item = {
                field: str(value) if hasattr(value, "hex") else value
                for field, value in zip(fields[dimension], key, strict=True)
            }
            item.update(self._metrics(rows))
            items.append(item)
        items.sort(key=lambda item: (Decimal(item["settled_amount"]), item["succeeded_count"]), reverse=True)
        total = len(items)
        return total, items[(page - 1) * page_size : page * page_size]

    def _collect(self, *, start_date: date, end_date: date, filters: dict) -> list[dict]:
        realtime_start = datetime.now(SHANGHAI).date() - timedelta(days=REALTIME_DAYS - 1)
        rows: list[dict] = []
        if start_date < realtime_start:
            history_end = min(end_date, realtime_start)
            for item in self._crud.list_daily_statistics(start_date=start_date, end_date=history_end, filters=filters):
                rows.append(self._daily_row(item))
        if end_date > realtime_start:
            current_start = max(start_date, realtime_start)
            start_at, _ = self._day_bounds(current_start)
            _, end_at = self._day_bounds(end_date)
            for item in self._crud.list_statistics_records(start_at=start_at, end_at=end_at, filters=filters):
                rows.append(self._record_row(item))
        return rows

    @staticmethod
    def _record_row(record) -> dict:
        return {
            "stat_date": record.created_at.astimezone(SHANGHAI).date(),
            "user_id": record.user_id,
            "access_token_id": record.access_token_id,
            "token_display_name": record.token_display_name,
            "request_type": record.request_type,
            "model_id": record.model_id,
            "model_name": record.model_name,
            "channel_id": record.channel_id,
            "channel_name": record.channel_name,
            "provider_name": record.provider_name,
            "succeeded_count": int(record.status == UsageRecordStatus.succeeded),
            "refunded_count": int(record.status == UsageRecordStatus.refunded),
            "settled_amount": record.amount if record.status == UsageRecordStatus.succeeded else Decimal("0"),
            "total_duration_ms": (record.duration_ms or 0) if record.status == UsageRecordStatus.succeeded else 0,
        }

    @staticmethod
    def _daily_row(item) -> dict:
        return {
            "stat_date": item.stat_date,
            "user_id": item.user_id,
            "access_token_id": item.access_token_id,
            "token_display_name": item.token_display_name,
            "request_type": item.request_type,
            "model_id": item.model_id,
            "model_name": item.model_name,
            "channel_id": item.channel_id,
            "channel_name": item.channel_name,
            "provider_name": item.provider_name,
            "succeeded_count": item.succeeded_count,
            "refunded_count": item.refunded_count,
            "settled_amount": item.settled_amount,
            "total_duration_ms": item.total_duration_ms,
        }

    @staticmethod
    def _metrics(rows: list[dict]) -> dict:
        succeeded_count = sum(item["succeeded_count"] for item in rows)
        refunded_count = sum(item["refunded_count"] for item in rows)
        settled_amount = sum((item["settled_amount"] for item in rows), Decimal("0"))
        total_duration_ms = sum(item["total_duration_ms"] for item in rows)
        total_terminal = succeeded_count + refunded_count
        return {
            "succeeded_count": succeeded_count,
            "refunded_count": refunded_count,
            "settled_amount": str(settled_amount),
            "success_rate": str(Decimal(succeeded_count) / total_terminal if total_terminal else Decimal("0")),
            "average_duration_ms": total_duration_ms // succeeded_count if succeeded_count else 0,
        }

    @staticmethod
    def _day_bounds(stat_date: date) -> tuple[datetime, datetime]:
        start_at = datetime.combine(stat_date, time.min, tzinfo=SHANGHAI)
        return start_at.astimezone(UTC), (start_at + timedelta(days=1)).astimezone(UTC)

    @staticmethod
    def _resolve_range(
        *, range_name: str | None, start_at: datetime | None, end_at: datetime | None
    ) -> tuple[date, date]:
        if (start_at is None) != (end_at is None):
            raise UsageStatisticsValidationError("开始与结束时间必须同时提供")
        if start_at is not None and end_at is not None:
            if start_at.tzinfo is None or end_at.tzinfo is None:
                raise UsageStatisticsValidationError("时间必须包含时区")
            local_start = start_at.astimezone(SHANGHAI).date()
            local_end = end_at.astimezone(SHANGHAI).date()
            if end_at <= start_at or local_end <= local_start:
                raise UsageStatisticsValidationError("结束时间必须晚于开始时间")
            if local_end - local_start > timedelta(days=366):
                raise UsageStatisticsValidationError("统计范围不能超过366天")
            return local_start, local_end
        today = datetime.now(SHANGHAI).date()
        ranges = {"today": 1, "last_7_days": 7, "last_30_days": 30}
        days = ranges.get(range_name or "last_30_days")
        if days is None:
            raise UsageStatisticsValidationError("时间范围不合法")
        return today - timedelta(days=days - 1), today + timedelta(days=1)
