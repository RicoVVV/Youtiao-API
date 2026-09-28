"""使用记录接口 DTO。"""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class UsageRecordListQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    request_type: str | None = Field(default=None, min_length=1, max_length=64)
    model_name: str | None = Field(default=None, min_length=1, max_length=64)
    token_display_name: str | None = Field(default=None, min_length=1, max_length=128)
    status: str | None = Field(default=None, min_length=1, max_length=32)


class AdminUsageRecordListQuery(UsageRecordListQuery):
    user_id: UUID | None = None
    channel_id: UUID | None = None
    provider_name: str | None = Field(default=None, min_length=1, max_length=64)
    username: str | None = Field(default=None, min_length=1, max_length=128)


class UsageRecordDetailQuery(BaseModel):
    usage_record_id: UUID


class UsageStatisticsQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    range: Literal["today", "last_7_days", "last_30_days"] | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    request_type: str | None = Field(default=None, min_length=1, max_length=64)
    model_id: UUID | None = None
    channel_id: UUID | None = None
    provider_name: str | None = Field(default=None, min_length=1, max_length=64)
    access_token_id: UUID | None = None


class UsageStatisticsModelsQuery(UsageStatisticsQuery):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class AdminUsageStatisticsQuery(UsageStatisticsQuery):
    user_id: UUID | None = None


class UsageStatisticsDimensionQuery(AdminUsageStatisticsQuery):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    dimension: Literal["user", "model", "channel", "provider", "token"]


def usage_record_response(record, *, detail: bool, include_admin_fields: bool) -> dict[str, Any]:
    payload = {
        "id": str(record.id),
        "request_type": record.request_type,
        "token_display_name": record.token_display_name,
        "model_name": record.model_name,
        "status": record.status.value,
        "amount": str(record.amount),
        "created_at": record.created_at,
        "started_at": record.started_at,
        "completed_at": record.completed_at,
        "duration_ms": record.duration_ms,
        "first_token_duration_ms": record.first_token_duration_ms,
        "prompt_tokens": record.prompt_tokens,
        "completion_tokens": record.completion_tokens,
        "cached_tokens": record.cached_tokens,
        "cache_write_tokens": record.cache_write_tokens,
    }
    if include_admin_fields:
        payload["username"] = record.user.username
        payload["channel_name"] = record.channel_name
        payload["provider_name"] = record.provider_name
    if include_admin_fields and record.resource_type == "video_task" and record.resource_id is not None:
        payload["upstream_task_id"] = getattr(record, "_upstream_task_id", None)
    if detail:
        payload["request_id"] = record.request_id
        payload["request_payload"] = record.request_payload
        payload["public_response_payload"] = record.public_response_payload
        if include_admin_fields:
            payload["upstream_response_payload"] = record.upstream_response_payload or record.response_metadata
    return payload
