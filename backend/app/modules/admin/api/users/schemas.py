"""管理员用户管理 HTTP 契约，仅定义创建与查询用户的请求和响应模型。"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class AdminUserCreateRequest(BaseModel):
    """管理员创建用户时提交的账号与初始密码。"""

    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=8, max_length=256)


class AdminUserCreateResponse(BaseModel):
    """管理员创建用户后的安全身份投影。"""

    user_id: UUID
    username: str


class AdminUserListItem(BaseModel):
    """管理员用户列表中的安全用户投影。"""

    id: UUID
    username: str
    is_active: bool
    is_admin: bool
    created_at: datetime
    balance: str
    usage: str
    active_lease_count: int


class AdminUserListResponse(BaseModel):
    """管理员查询用户列表时返回的页码、总数和安全用户投影。"""

    items: list[AdminUserListItem]
    total: int
    page: int
    page_size: int
