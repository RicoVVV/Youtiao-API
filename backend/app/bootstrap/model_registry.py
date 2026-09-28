"""集中注册 ORM 模型，确保应用、Worker 和迁移进程完整加载元数据。"""

from app.modules.billing.model import BillingAdjustment, Charge, PriceQuote, RedemptionCode
from app.modules.channels.model.channel import Channel
from app.modules.channels.model.concurrency import UserConcurrencyLease, UserModelConcurrencyOverride
from app.modules.models.model import Model, ModelRoute
from app.modules.monitoring.model import (
    GroupMetricSnapshot,
    MonitorAlert,
    MonitorAlertRule,
    MonitorNotification,
    MonitorResourceRule,
    ServerMetricSnapshot,
)
from app.modules.payment.model import PaymentOption
from app.modules.pricing.model.pricing import PricingModifier, PricingRule
from app.modules.pricing.model.pricing_item import PricingItem
from app.modules.system_settings.model import SystemSetting
from app.modules.system_tasks.model.system_task import SystemTask
from app.modules.usage.model import UsageDailyStatistic, UsageRecord
from app.modules.user.model.auth_session import AuthSession
from app.modules.user.model.refresh_token import RefreshToken
from app.modules.user.model.token import Token
from app.modules.user.model.token_group import TokenGroup, TokenGroupBinding, TokenGroupUser
from app.modules.user.model.user import User
from app.modules.video.model.input_material import VideoInputMaterial
from app.modules.video.model.video_task import TaskEvent, VideoTask
from app.modules.wallet.model import BalanceRecord, RechargeOrder, Wallet

__all__ = [
    "Token",
    "TokenGroup",
    "TokenGroupUser",
    "TokenGroupBinding",
    "AuthSession",
    "RefreshToken",
    "BillingAdjustment",
    "RedemptionCode",
    "Charge",
    "BalanceRecord",
    "UsageRecord",
    "UsageDailyStatistic",
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
    "UserConcurrencyLease",
    "UserModelConcurrencyOverride",
    "PaymentOption",
    "SystemSetting",
    "GroupMetricSnapshot",
    "MonitorAlert",
    "MonitorAlertRule",
    "MonitorNotification",
    "MonitorResourceRule",
    "ServerMetricSnapshot",
]


def load_models() -> None:
    """显式加载全部 ORM 模型，确保跨领域关系和 Alembic 元数据完成注册。"""
