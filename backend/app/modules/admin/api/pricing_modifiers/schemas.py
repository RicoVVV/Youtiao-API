from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class PricingModifierCreateRequest(BaseModel):
    pricing_rule_id: UUID
    name: str = Field(min_length=1, max_length=128)
    priority: int
    conditions: list[dict[str, Any]] = Field(default_factory=list)
    effect_type: Literal["multiplier", "fixed_price"]
    effect_payload: dict[str, Any] = Field(default_factory=dict)
    scope_type: Literal["item_ids", "item_kind", "all_items"] = "all_items"
    scope_item_ids: list[str] = Field(default_factory=list)
    scope_item_kinds: list[str] = Field(default_factory=list)
    active: bool = True


class PricingModifierUpdateRequest(PricingModifierCreateRequest):
    pricing_modifier_id: UUID


class PricingModifierDeleteRequest(BaseModel):
    pricing_modifier_id: UUID


class PricingModifierCopyRequest(BaseModel):
    pricing_modifier_id: UUID
