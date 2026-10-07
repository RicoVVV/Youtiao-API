"""管理员 Token 分组 RPC API 的请求与响应契约。

本模块仅定义 Token 分组增删改查的数据校验规则，不包含鉴权、事务或业务编排。
"""

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class AdminTokenGroupCreateRequest(BaseModel):
    """描述创建 Token 分组时提交的名称、展示属性和初始授权用户。"""

    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=512)
    visibility: str = Field(pattern="^(public|restricted)$")
    is_active: bool = True
    price_multiplier: Decimal = Field(default=Decimal("1.000000"), gt=0, max_digits=18, decimal_places=6)
    user_ids: list[UUID] = Field(default_factory=list)


class AdminTokenGroupUpdateRequest(BaseModel):
    """描述按字段更新 Token 分组时提交的目标标识和可变字段。"""

    group_id: int
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=512)
    visibility: str | None = Field(default=None, pattern="^(public|restricted)$")
    is_active: bool | None = None
    price_multiplier: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=6)
    user_ids: list[UUID] | None = None


class AdminTokenGroupDeleteRequest(BaseModel):
    """描述逻辑删除 Token 分组时提交的目标标识。"""

    group_id: int


class AdminTokenGroupUserResponse(BaseModel):
    """描述受限 Token 分组中被授权用户的展示信息。"""

    id: UUID
    username: str


class AdminTokenGroupResponse(BaseModel):
    """描述管理员查询或维护 Token 分组时返回的完整管理投影。"""

    id: int
    name: str
    description: str
    visibility: str
    is_active: bool
    is_default: bool
    price_multiplier: Decimal
    users: list[AdminTokenGroupUserResponse]


class AdminTokenGroupListResponse(BaseModel):
    """描述管理员分页查询 Token 分组时返回的分页结果。"""

    items: list[AdminTokenGroupResponse]
    total: int
    page: int
    page_size: int
