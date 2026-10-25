"""管理员账务 HTTP 请求 DTO。"""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import AliasChoices, BaseModel, Field, field_validator


class AdjustmentRequest(BaseModel):
    """管理员调整用户余额的请求参数，正数入账、负数扣减。"""

    user_id: UUID
    amount: Decimal = Field(decimal_places=6)
    reason: str | None = Field(default=None, min_length=1, max_length=256)

    @field_validator("amount")
    @classmethod
    def _reject_zero_amount(cls, value: Decimal) -> Decimal:
        """调整金额必须非零，方向由正负号表达。"""

        if value == 0:
            raise ValueError("调整金额不能为 0")
        return value


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
    """管理员更新未兑换兑换码运营信息的请求参数。

    ``code_id`` 兼容前端历史字段名 ``id``；前端统一改用 ``code_id`` 后即可移除该别名。
    """

    code_id: UUID = Field(validation_alias=AliasChoices("code_id", "id"))
    name: str = Field(min_length=1, max_length=128)
    remark: str | None = Field(default=None, max_length=512)
    expires_at: datetime | None = None


class RedemptionCodeStatusRequest(BaseModel):
    """管理员切换未兑换兑换码启用状态的请求参数。

    ``code_id`` 兼容前端历史字段名 ``id``；前端统一改用 ``code_id`` 后即可移除该别名。
    """

    code_id: UUID = Field(validation_alias=AliasChoices("code_id", "id"))
    active: bool


class RedemptionCodeDetailRequest(BaseModel):
    """管理员查询兑换码详情的请求参数。"""

    code_id: UUID
