"""同步生成应用层内部契约，承载跨异步边界冻结的计费与执行决策。

本模块只定义应用服务内部传递的不可变数据结构，不依赖 FastAPI、Pydantic 或数据库会话。
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.modules.pricing.model.pricing import PricingModifier, PricingRule
from app.modules.pricing.model.pricing_item import PricingItem
from app.modules.providers.contracts import GenerationProvider, ProviderUpload


@dataclass(frozen=True)
class GenerationBilling:
    """一次同步生成请求的冻结计费上下文。

    ``postpaid`` 为真表示按上游实际用量后付费，``reserved_amount`` 则为调用前的预占金额；
    ``plan`` 与 ``items`` 为命中的计费方案快照，用于结算时按实际用量重算并退款差额。
    """

    user_id: UUID
    access_token_id: UUID
    token_display_name: str | None
    token_group_id: int
    resource_id: UUID
    request_type: str
    resource_type: str
    model_id: UUID
    model_name: str
    channel_id: UUID
    channel_name: str
    provider_name: str
    request_payload: dict[str, Any]
    group_ids: list[int]
    postpaid: bool
    reserved_amount: Decimal
    pricing_context: dict[str, Any]
    priced_at: datetime
    token_group_price_multiplier: Decimal
    plan: PricingRule
    items: list[PricingItem]
    modifiers: list[PricingModifier]
    allowed_fields: list[str]


@dataclass(frozen=True)
class PreparedGeneration:
    """已完成选路、契约校验和计费预占的待执行生成请求。"""

    provider: GenerationProvider
    provider_request: dict[str, Any]
    billing: GenerationBilling
    uploads: list[ProviderUpload] = field(default_factory=list)
