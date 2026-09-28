"""管理员长期 Token 管理 HTTP 契约。"""

from uuid import UUID

from pydantic import BaseModel, Field


class AdminUserTokenRequest(BaseModel):
    """管理员为指定用户签发长期 Token 时提交的用户标识和展示标签。"""

    user_id: UUID
    label: str | None = Field(default=None, max_length=128)
    group_ids: list[int] = Field(min_length=1)


class AdminTokenResponse(BaseModel):
    """管理员新增长期 Token 后的响应。"""

    id: UUID
    user_id: UUID
    key_prefix: str
    token: str
