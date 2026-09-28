"""ORM 模型注册表，确保跨领域关系在应用、Worker 和迁移进程中完整加载。"""

from app.modules.billing.model import BillingAdjustment, Charge, PriceQuote, RedemptionCode
from app.modules.channels.model.channel import Channel
from app.modules.models.model import Model, ModelRoute
from app.modules.pricing.model.pricing import PricingModifier, PricingRule
from app.modules.pricing.model.pricing_item import PricingItem
from app.modules.system_tasks.model.system_task import SystemTask
from app.modules.usage.model import UsageRecord
from app.modules.user.model.auth_session import AuthSession
from app.modules.user.model.refresh_token import RefreshToken
from app.modules.user.model.token import Token
from app.modules.user.model.user import User
from app.modules.video.model.input_material import VideoInputMaterial
from app.modules.video.model.video_task import TaskEvent, VideoTask
from app.modules.wallet.model import BalanceRecord, RechargeOrder, Wallet

__all__ = [
    "Token",
    "AuthSession",
    "RefreshToken",
    "BillingAdjustment",
    "RedemptionCode",
    "Charge",
    "BalanceRecord",
    "UsageRecord",
    "RechargeOrder",
    "PriceQuote",
    "Model",
    "Channel",
    "ModelRoute",
    "PricingRule",
    "PricingModifier",
    "PricingItem",
    "VideoInputMaterial",
    "SystemTask",
    "TaskEvent",
    "User",
    "VideoTask",
    "Wallet",
]


def load_models() -> None:
    """显式加载全部 ORM 模型，确保跨领域关系和 Alembic 元数据完整注册。"""
