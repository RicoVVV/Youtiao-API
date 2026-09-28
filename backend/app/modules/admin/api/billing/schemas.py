"""管理员账务 HTTP 请求 DTO。"""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class AdjustmentRequest(BaseModel):
    """管理员调整用户余额的请求参数。"""

    user_id: UUID
    amount: Decimal = Field(gt=0, decimal_places=6)
    reason: str | None = Field(default=None, min_length=1, max_length=256)


class RedemptionCodeRequest(BaseModel):
    """管理员生成固定金额兑换码的请求参数，quantity 大于 1 时批量生成。"""

    name: str = Field(min_length=1, max_length=128)
    amount: Decimal = Field(gt=0, decimal_places=6)
    remark: str | None = Field(default=None, max_length=512)
    expires_at: datetime | None = None
    quantity: int = Field(default=1, ge=1, le=1000)


class RedemptionCodeExportRequest(BaseModel):
    """管理员按筛选条件导出兑换码明文的请求参数。"""

    name: str | None = Field(default=None, min_length=1, max_length=128)
    status: Literal["unused", "disabled", "expired", "redeemed"] | None = None


class RedemptionCodeListRequest(BaseModel):
    """管理员分页筛选兑换码的请求参数。"""

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    name: str | None = Field(default=None, min_length=1, max_length=128)
    status: Literal["unused", "disabled", "expired", "redeemed"] | None = None


class RedemptionCodeUpdateRequest(BaseModel):
    """管理员更新未兑换兑换码运营信息的请求参数。"""

    code_id: UUID
    name: str = Field(min_length=1, max_length=128)
    remark: str | None = Field(default=None, max_length=512)
    expires_at: datetime | None = None


class RedemptionCodeStatusRequest(BaseModel):
    """管理员切换未兑换兑换码启用状态的请求参数。"""

    code_id: UUID
    active: bool


class RedemptionCodeDetailRequest(BaseModel):
    """管理员查询兑换码详情的请求参数。"""

    code_id: UUID
