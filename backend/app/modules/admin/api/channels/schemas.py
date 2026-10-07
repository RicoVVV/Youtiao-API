from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ChannelCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    base_url: str = Field(min_length=9, max_length=512)
    api_key: str = Field(min_length=1, max_length=4096)
    config: dict[str, Any] = Field(default_factory=dict)
    supported_models: list[str] = Field(default_factory=list)
    token_group_ids: list[int] = Field(default_factory=list)
    model_mapping: dict[str, str] = Field(default_factory=dict)
    param_override: dict[str, Any] = Field(default_factory=dict)
    header_override: dict[str, Any] = Field(default_factory=dict)
    priority: int = 0
    weight: int = Field(default=1, ge=1)
    active: bool = True
    healthy: bool = True


class ChannelUpdateRequest(ChannelCreateRequest):
    channel_id: UUID
    api_key: str | None = Field(default=None, min_length=1, max_length=4096)


class ChannelStatusUpdateRequest(BaseModel):
    channel_id: UUID
    active: bool


class ChannelDeleteRequest(BaseModel):
    channel_id: UUID


class ChannelCopyRequest(BaseModel):
    channel_id: UUID


class ChannelTestRequest(BaseModel):
    channel_id: UUID
    model: str | None = Field(default=None, min_length=1, max_length=64)


class ChannelLatestTestSnapshotResponse(BaseModel):
    tested_at: str
    status: Literal["succeeded", "failed"]
    model: str
    model_type: Literal["text", "image"]
    duration_ms: int
    amount: Decimal
    error_code: str | None = None
    message: str | None = None
    usage: dict[str, int | str] = Field(default_factory=dict)


class ChannelTestResultResponse(BaseModel):
    success: bool
    message: str
    time: float
    amount: Decimal = Decimal("0")
    result: dict[str, Any] | None = None
