from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class PricingItemRequest(BaseModel):
    label: str = Field(min_length=1, max_length=128)
    position: int = Field(ge=0)
    kind: str
    source_fields: list[str] = Field(default_factory=list)
    estimate_config: dict[str, int | str] = Field(default_factory=dict)
    free_quantity: int = Field(default=0, ge=0)
    unit_amount: str | None = Field(
        default=None,
        description="基础单价；文本 Token 计费项按元 / 1M Token，其余项目按对应计量单位",
    )
    active: bool = True


class PricingRuleCreateRequest(BaseModel):
    model_id: UUID
    token_group_id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=128)
    priority: int
    conditions: list[dict[str, Any]] = Field(default_factory=list)
    items: list[PricingItemRequest] = Field(min_length=1)
    currency: str = Field(default="USD", min_length=1, max_length=8)
    active: bool = True


class PricingRuleUpdateRequest(PricingRuleCreateRequest):
    pricing_rule_id: UUID


class PricingRuleDeleteRequest(BaseModel):
    pricing_rule_id: UUID


class PricingRuleCopyRequest(BaseModel):
    pricing_rule_id: UUID
