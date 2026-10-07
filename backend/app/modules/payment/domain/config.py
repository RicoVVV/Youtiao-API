"""支付领域配置：定义公共定价、渠道凭据和支付方式级启停快照。"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from types import MappingProxyType
from uuid import UUID

ALIPAY_OFFICIAL = "alipay_official"
EPAY = "epay"
STRIPE = "stripe"


@dataclass(frozen=True, slots=True)
class PaymentPricingConfig:
    """保存所有支付服务商共用的充值定价规则。"""

    min_topup: Decimal
    max_topup: Decimal
    amount_options: tuple[Decimal, ...]
    amount_discount: Mapping[Decimal, Decimal]
    group_ratios: Mapping[str, Decimal]


@dataclass(frozen=True, slots=True)
class PaymentProviderRuntimeConfig:
    """保存所有支付服务商通用的运行时配置，不包含专属密钥。"""

    provider: str
    gateway_url: str
    callback_url: str
    return_url: str
    payment_methods: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PaymentDisplayMethodConfig:
    """保存充值页支付方式的展示信息和独立充值金额范围。"""

    payment_name: str
    payment_channel: str
    payment_method: str
    payment_icon: str
    enabled: bool
    min_topup: Decimal | None
    max_topup: Decimal | None


@dataclass(frozen=True, slots=True)
class AlipayOfficialRuntimeConfig(PaymentProviderRuntimeConfig):
    """保存支付宝官方页面支付所需的应用凭据。"""

    app_id: str
    private_key: str
    public_key: str
    seller_id: str | None = None


@dataclass(frozen=True, slots=True)
class EpayRuntimeConfig(PaymentProviderRuntimeConfig):
    """保存易支付商户账户共用的凭据，多个支付方式共用此配置。"""

    partner_id: str
    private_key: str
    platform_public_key: str


@dataclass(frozen=True, slots=True)
class StripeRuntimeConfig(PaymentProviderRuntimeConfig):
    """保存 Stripe Checkout 所需的密钥、模式和固定美元收款币种配置。"""

    api_key: str
    webhook_secret: str
    cancel_url: str = ""
    mode: str = "test"
    currency: str = "USD"


@dataclass(frozen=True, slots=True)
class PaymentRuntimeConfig:
    """保存进程发布的完整支付快照，提供 Provider 到类型化配置的只读映射。"""

    pricing: PaymentPricingConfig
    providers: Mapping[str, PaymentProviderRuntimeConfig]
    compliance_confirmed: bool = False
    compliance_terms_version: str = ""
    compliance_confirmed_at: datetime | None = None
    compliance_confirmed_by: UUID | None = None
    compliance_confirmed_ip: str | None = None
    payments: tuple[PaymentDisplayMethodConfig, ...] = ()

    def find_payment(self, payment_channel: str, payment_method: str) -> PaymentDisplayMethodConfig | None:
        """按支付渠道和支付方式查找其展示和金额配置。

        作用：让报价和下单服务使用管理员配置的方式级充值范围。
        使用位置：各支付应用服务在计算金额前调用。
        传入参数：payment_channel 为支付渠道标识；payment_method 为下单使用的渠道内支付方式。
        返回参数：找到时返回对应支付方式配置；未配置时返回 None。
        """
        return next(
            (
                item
                for item in self.payments
                if item.payment_channel == payment_channel and item.payment_method == payment_method
            ),
            None,
        )

    @staticmethod
    def freeze(config: "PaymentRuntimeConfig") -> "PaymentRuntimeConfig":
        """复制并冻结快照中的映射，供缓存发布与读取时调用。

        作用：避免调用方修改已发布配置导致请求之间观察到不同状态。
        使用位置：PaymentSettingsRuntime.replace 和 get 在发布或返回快照前调用。
        传入参数：config 为待发布或读取的支付运行时配置。
        返回参数：返回其映射均不可修改的独立快照。
        """

        pricing = PaymentPricingConfig(
            config.pricing.min_topup,
            config.pricing.max_topup,
            tuple(config.pricing.amount_options),
            MappingProxyType(dict(config.pricing.amount_discount)),
            MappingProxyType(dict(config.pricing.group_ratios)),
        )
        return PaymentRuntimeConfig(
            pricing=pricing,
            providers=MappingProxyType(dict(config.providers)),
            compliance_confirmed=config.compliance_confirmed,
            compliance_terms_version=config.compliance_terms_version,
            compliance_confirmed_at=config.compliance_confirmed_at,
            compliance_confirmed_by=config.compliance_confirmed_by,
            compliance_confirmed_ip=config.compliance_confirmed_ip,
            payments=tuple(config.payments),
        )
