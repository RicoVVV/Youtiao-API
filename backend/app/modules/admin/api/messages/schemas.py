"""管理员消息 RPC API 的请求与响应契约。

本模块仅定义消息管理端接口的数据校验规则，不包含鉴权、事务或业务编排。
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.modules.message.model import MessageType


def _require_timezone(value: datetime | None) -> datetime | None:
    """校验时间必须携带时区信息。"""

    if value is not None and value.tzinfo is None:
        raise ValueError("时间必须包含时区")
    return value


class AdminMessageTargetsRequest(BaseModel):
    """描述消息的定向目标集合，两类目标均为可选。"""

    user_ids: list[UUID] = Field(default_factory=list)
    token_group_ids: list[int] = Field(default_factory=list)


class AdminMessageCreateRequest(BaseModel):
    """描述创建消息时提交的内容、可见范围、生效时间与定向目标。"""

    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1)
    type: MessageType
    is_public: bool = False
    is_active: bool = True
    start_at: datetime
    expires_at: datetime | None = None
    targets: AdminMessageTargetsRequest = Field(default_factory=AdminMessageTargetsRequest)

    @field_validator("start_at", "expires_at")
    @classmethod
    def _validate_timezone(cls, value: datetime | None) -> datetime | None:
        return _require_timezone(value)


class AdminMessageUpdateRequest(BaseModel):
    """描述按字段更新消息时提交的目标标识与可变字段。"""

    message_id: UUID
    title: str | None = Field(default=None, min_length=1, max_length=255)
    content: str | None = Field(default=None, min_length=1)
    type: MessageType | None = None
    is_public: bool | None = None
    is_active: bool | None = None
    start_at: datetime | None = None
    expires_at: datetime | None = None
    targets: AdminMessageTargetsRequest | None = None

    @field_validator("start_at", "expires_at")
    @classmethod
    def _validate_timezone(cls, value: datetime | None) -> datetime | None:
        return _require_timezone(value)


class AdminMessageStatusRequest(BaseModel):
    """描述启用或下架消息时提交的目标标识与目标状态。"""

    message_id: UUID
    is_active: bool


class AdminMessageDeleteRequest(BaseModel):
    """描述逻辑删除消息时提交的目标标识。"""

    message_id: UUID


class AdminMessageTargetsResponse(BaseModel):
    """描述消息当前生效的定向目标。"""

    user_ids: list[UUID]
    token_group_ids: list[int]


class AdminMessageResponse(BaseModel):
    """描述管理员查询或维护消息时返回的完整管理投影。"""

    id: UUID
    title: str
    content: str
    type: MessageType
    is_public: bool
    is_active: bool
    start_at: datetime
    expires_at: datetime | None
    created_at: datetime | None
    updated_at: datetime | None
    targets: AdminMessageTargetsResponse


class AdminMessageListResponse(BaseModel):
    """描述管理员分页查询消息时返回的分页结果。"""

    items: list[AdminMessageResponse]
    total: int
    page: int
    page_size: int
