"""会员用户端与管理端 RPC API 的请求与响应契约。

本模块仅定义数据校验规则，不包含鉴权、事务或业务编排。
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

_PERIOD_PATTERN = "^(week|month)$"
_CODE_PATTERN = "^[a-z0-9_-]{1,32}$"


class MembershipGroupResponse(BaseModel):
    """描述会员专享分组的展示信息。"""

    id: int
    name: str


class MembershipLevelResponse(BaseModel):
    """描述会员等级的展示信息。"""

    id: UUID
    code: str
    name: str
    description: str
    rank: int


class MembershipPlanResponse(BaseModel):
    """描述会员套餐的展示信息，金额为两位小数字符串。"""

    id: UUID
    period: str
    price: str
    bonus_amount: str


class MembershipPublicLevelResponse(MembershipLevelResponse):
    """描述对外售卖等级及其套餐与专享分组。"""

    groups: list[MembershipGroupResponse]
    plans: list[MembershipPlanResponse]


class MembershipPublicPlanListResponse(BaseModel):
    """描述对外可购买会员套餐列表。"""

    items: list[MembershipPublicLevelResponse]


# 管理端


class AdminMembershipPlanInput(BaseModel):
    """描述创建等级时一并创建的套餐。"""

    period: str = Field(pattern=_PERIOD_PATTERN)
    price: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    bonus_amount: Decimal = Field(default=Decimal("0"), ge=0, max_digits=12, decimal_places=2)
    is_active: bool = True


class AdminMembershipLevelCreateRequest(BaseModel):
    """描述创建会员等级时提交的字段，可选附带套餐与专享分组。"""

    code: str = Field(pattern=_CODE_PATTERN)
    name: str = Field(min_length=1, max_length=64)
    description: str = Field(default="", max_length=512)
    rank: int = Field(ge=1)
    is_public: bool = False
    is_active: bool = True
    plans: list[AdminMembershipPlanInput] | None = None
    group_ids: list[int] | None = None


class AdminMembershipLevelUpdateRequest(BaseModel):
    """描述按字段更新会员等级；group_ids 提供时整体替换专享分组。"""

    level_id: UUID
    name: str | None = Field(default=None, min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=512)
    rank: int | None = Field(default=None, ge=1)
    is_public: bool | None = None
    group_ids: list[int] | None = None


class AdminMembershipLevelStatusRequest(BaseModel):
    """描述启用或停用会员等级。"""

    level_id: UUID
    is_active: bool


class AdminMembershipLevelDeleteRequest(BaseModel):
    """描述逻辑删除会员等级。"""

    level_id: UUID


class AdminMembershipPlanResponse(MembershipPlanResponse):
    """描述套餐管理投影。"""

    level_id: UUID
    is_active: bool
    created_at: datetime | None
    updated_at: datetime | None


class AdminMembershipLevelResponse(MembershipLevelResponse):
    """描述等级管理投影，含套餐与专享分组。"""

    is_public: bool
    is_active: bool
    created_at: datetime | None
    updated_at: datetime | None
    plans: list[AdminMembershipPlanResponse]
    groups: list[MembershipGroupResponse]


class AdminMembershipLevelListResponse(BaseModel):
    """描述等级分页结果。"""

    items: list[AdminMembershipLevelResponse]
    total: int
    page: int
    page_size: int


class AdminMembershipPlanCreateRequest(BaseModel):
    """描述为等级新增套餐。"""

    level_id: UUID
    period: str = Field(pattern=_PERIOD_PATTERN)
    price: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    bonus_amount: Decimal = Field(default=Decimal("0"), ge=0, max_digits=12, decimal_places=2)
    is_active: bool = True


class AdminMembershipPlanUpdateRequest(BaseModel):
    """描述更新套餐价格与赠送额。"""

    plan_id: UUID
    price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    bonus_amount: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)


class AdminMembershipPlanStatusRequest(BaseModel):
    """描述启用或停用套餐。"""

    plan_id: UUID
    is_active: bool


class AdminMembershipPlanDeleteRequest(BaseModel):
    """描述逻辑删除套餐。"""

    plan_id: UUID


class AdminUserMembershipResponse(BaseModel):
    """描述用户会员管理投影。"""

    id: UUID
    user_id: UUID
    level_id: UUID
    level_code: str | None
    level_name: str | None
    started_at: datetime
    expires_at: datetime
    is_active: bool


class AdminUserMembershipListResponse(BaseModel):
    """描述用户会员分页结果。"""

    items: list[AdminUserMembershipResponse]
    total: int
    page: int
    page_size: int


class AdminMembershipRecordResponse(BaseModel):
    """描述管理端会员流水，含用户与操作人。"""

    id: UUID
    user_id: UUID
    source: str
    level_id: UUID
    level_name: str | None
    plan_id: UUID | None
    quantity: int
    expires_before: datetime | None
    expires_after: datetime | None
    bonus_amount: str
    recharge_order_id: UUID | None
    operator_id: UUID | None
    reason: str
    created_at: datetime | None


class AdminMembershipRecordListResponse(BaseModel):
    """描述管理端会员流水分页结果。"""

    items: list[AdminMembershipRecordResponse]
    total: int
    page: int
    page_size: int


class AdminUserMembershipGrantRequest(BaseModel):
    """描述管理员授予用户会员。"""

    user_id: UUID
    plan_id: UUID
    quantity: int = Field(default=1, ge=1, le=12)
    grant_bonus: bool = False
    reason: str = Field(default="", max_length=256)


class AdminUserMembershipRevokeRequest(BaseModel):
    """描述管理员撤销用户会员。"""

    user_id: UUID
    reason: str = Field(default="", max_length=256)
