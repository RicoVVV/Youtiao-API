"""定义支付接口的请求与响应 DTO，统一校验创建订单、报价和配置数据。"""

import re
from datetime import datetime
from typing import Annotated, Literal
from urllib.parse import urlparse
from uuid import UUID

from pydantic import BaseModel, Field, StrictStr, field_validator, model_validator

_AMOUNT_PATTERN = re.compile(r"^\d+(?:\.\d{1,2})?$")


class AmountRequest(BaseModel):
    """定义用户试算或下单时提交的充值金额。"""

    amount: StrictStr = Field(min_length=1, max_length=32)

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, value: str) -> str:
        """限制金额为最多两位小数的普通十进制字符串。

        作用：在 HTTP 边界拒绝浮点数、科学计数法和不确定精度的金额输入。
        使用位置：Pydantic 解析 AmountRequest 及其子模型时自动调用。
        传入参数：value 为请求 JSON 中的 amount 字符串。
        返回参数：返回经格式确认的原金额字符串；格式错误时抛出 ValueError。
        """
        if not _AMOUNT_PATTERN.fullmatch(value):
            raise ValueError("充值金额必须是最多两位小数的正数")
        return value


class ProviderOrderRequest(AmountRequest):
    """定义创建人民币支付订单的请求参数。

    作用：约束三种支付渠道创建订单时提交的金额、支付方式和支付完成跳转地址。
    使用位置：由支付宝官方、易支付和 Stripe 创建订单路由解析请求体时调用。
    传入参数：amount 为钱包充值金额；payment_method 为当前接口支持的支付方式；return_url 为支付完成后前端接收跳转的 HTTPS 地址。
    返回参数：返回完成格式校验的请求对象，供路由转换为应用层命令。
    """

    payment_method: StrictStr = Field(min_length=1, max_length=32)
    return_url: StrictStr = Field(min_length=1, max_length=2048)

    @field_validator("return_url")
    @classmethod
    def validate_return_url(cls, value: str) -> str:
        """校验支付完成后的跳转地址必须是完整 HTTPS 地址。

        作用：在 HTTP 边界拒绝空地址、相对路径和非 HTTPS 地址，保证三种支付网关都能安全使用该地址。
        使用位置：Pydantic 解析 ProviderOrderRequest 时自动调用，发生在路由创建应用层命令之前。
        传入参数：value 为前端请求中的 return_url。
        返回参数：返回校验通过的原地址；格式不符合要求时抛出 ValueError 并由接口返回 422。
        """
        parsed_url = urlparse(value)
        if parsed_url.scheme != "https" or not parsed_url.netloc:
            raise ValueError("return_url 必须是完整的 HTTPS 地址")
        return value


class PaymentQuoteRequest(AmountRequest):
    """定义统一金额试算接口的请求参数。"""

    payment_channel: StrictStr = Field(min_length=1, max_length=32, description="支付渠道标识")
    payment_method: StrictStr = Field(min_length=1, max_length=32, description="渠道内支付方式")


class PaymentProviderSettings(BaseModel):
    """定义管理员保存支付 Provider 时共用的非敏感字段。"""

    provider: str
    gateway_url: str = ""
    payment_methods: list[StrictStr] = Field(default_factory=list)


class AlipayOfficialSettings(PaymentProviderSettings):
    """定义支付宝官方 Provider 的管理配置字段。"""

    provider: Literal["alipay_official"]
    app_id: str = ""
    merchant_private_key: str | None = None
    public_key: str | None = None
    seller_id: str | None = None


class EpaySettings(PaymentProviderSettings):
    """定义易支付 Provider 的管理配置字段，微信和支付宝共用商户凭据。"""

    provider: Literal["epay"]
    partner_id: str = ""
    merchant_private_key: str | None = None
    platform_public_key: str | None = None


class StripeSettings(PaymentProviderSettings):
    """定义 Stripe Checkout 的管理员配置字段。"""

    provider: Literal["stripe"]
    api_key: str | None = None
    webhook_secret: str | None = None
    mode: Literal["test", "live"] = "test"
    currency: Literal["USD"] = "USD"

    gateway_url: str = "https://api.stripe.com"
    cancel_url: str = ""


ProviderSettingsRequest = Annotated[
    AlipayOfficialSettings | EpaySettings | StripeSettings, Field(discriminator="provider")
]


class PaymentProvidersRequest(BaseModel):
    """管理员提交的支付渠道配置对象，使用渠道标识作为对象键。"""

    epay: EpaySettings | None = Field(default=None, description="易支付渠道配置")
    stripe: StripeSettings | None = Field(default=None, description="Stripe 渠道配置")
    alipay_official: AlipayOfficialSettings | None = Field(default=None, description="支付宝官方渠道配置")

    @model_validator(mode="after")
    def validate_provider_keys(self) -> "PaymentProvidersRequest":
        """校验渠道对象键和内部渠道标识是否一致。

        作用：避免客户端把一个渠道配置错误保存到另一个渠道的配置空间。
        使用位置：解析管理员更新支付配置请求时由 Pydantic 自动调用。
        传入参数：无，使用当前已解析的渠道对象进行校验。
        返回参数：返回校验通过的当前对象；不一致时抛出参数校验错误。
        """
        for provider_key, provider in self.items():
            if provider is not None and provider.provider != provider_key:
                raise ValueError(f"providers.{provider_key}.provider 必须为 {provider_key}")
        return self

    def items(self) -> tuple[tuple[str, ProviderSettingsRequest | None], ...]:
        """按稳定顺序返回渠道对象键和对应配置。

        作用：让接口映射层不需要知道 Pydantic 字段细节即可遍历渠道配置。
        使用位置：管理员支付配置请求映射为应用层命令时调用。
        传入参数：无。
        返回参数：返回渠道名称与可选渠道配置组成的元组。
        """
        return (("epay", self.epay), ("stripe", self.stripe), ("alipay_official", self.alipay_official))

    def configured_providers(self) -> tuple[ProviderSettingsRequest, ...]:
        """返回请求中实际提交的渠道配置。

        作用：过滤未提交的可选渠道，供应用层只更新本次提供的渠道。
        使用位置：管理员支付配置请求映射时调用。
        传入参数：无。
        返回参数：返回已提供渠道配置的有序元组。
        """
        return tuple(provider for _, provider in self.items() if provider is not None)


class PaymentDisplayMethodRequest(BaseModel):
    """管理员提交的支付方式展示信息和独立充值金额范围。"""

    payment_name: StrictStr = Field(min_length=1, max_length=64, description="充值页显示的支付方式名称")
    payment_channel: StrictStr = Field(min_length=1, max_length=32, description="支付渠道标识，例如 epay 或 stripe")
    payment_method: StrictStr = Field(
        min_length=1, max_length=32, description="原始支付方式值，例如 alipay、wxpay、card"
    )
    payment_icon: StrictStr = Field(default="", max_length=2048, description="支付方式图标 HTTPS 地址")
    enabled: bool = Field(default=False, description="是否允许用户使用该支付方式")
    min_topup: StrictStr | None = Field(
        default=None, min_length=1, max_length=32, description="可选的支付方式最低充值金额"
    )
    max_topup: StrictStr | None = Field(
        default=None, min_length=1, max_length=32, description="可选的支付方式最高充值金额"
    )

    @field_validator("min_topup", "max_topup", mode="before")
    @classmethod
    def validate_topup_amount(cls, value: str | None) -> str | None:
        """校验支付方式独立充值金额采用标准两位小数以内格式。

        作用：在 HTTP 边界拒绝浮点数、科学计数法和不确定精度金额。
        使用位置：解析管理员更新支付配置请求时由 Pydantic 自动调用。
        传入参数：value 为请求中的最低或最高充值金额字符串。
        返回参数：返回格式正确的原始金额字符串；格式错误时抛出参数校验错误。
        """
        if value == "":
            return None
        if value is not None and not _AMOUNT_PATTERN.fullmatch(value):
            raise ValueError("充值金额必须是最多两位小数的正数")
        return value


class PaymentPricingRequest(BaseModel):
    """管理员提交的公共充值金额范围、快捷金额和折扣配置。"""

    min_topup: StrictStr = Field(default="0.01", min_length=1, max_length=32, description="公共最低充值金额")
    max_topup: StrictStr = Field(default="10000.00", min_length=1, max_length=32, description="公共最高充值金额")
    amount_options: list[StrictStr] = Field(
        default_factory=lambda: ["100.00", "200.00", "300.00", "500.00", "1000.00"], description="快捷充值金额列表"
    )
    amount_discount: dict[StrictStr, StrictStr] = Field(
        default_factory=lambda: {
            "100.00": "0.99",
            "200.00": "0.98",
            "300.00": "0.97",
            "500.00": "0.96",
            "1000.00": "0.95",
        },
        description="快捷金额对应的折扣倍率",
    )
    group_ratios: dict[StrictStr, StrictStr] = Field(
        default_factory=lambda: {"default": "1.00"}, description="用户分组充值倍率"
    )

    @field_validator("min_topup", "max_topup")
    @classmethod
    def validate_topup_amount(cls, value: str) -> str:
        """校验公共充值金额采用标准两位小数以内格式。

        作用：在 HTTP 边界拒绝不确定精度金额，保持公共范围可用于所有支付方式。
        使用位置：解析管理员更新支付配置请求时由 Pydantic 自动调用。
        传入参数：value 为公共最低或最高充值金额字符串。
        返回参数：返回格式正确的原始金额字符串；格式错误时抛出参数校验错误。
        """
        if not _AMOUNT_PATTERN.fullmatch(value):
            raise ValueError("充值金额必须是最多两位小数的正数")
        return value


class PaymentSettingsRequest(BaseModel):
    """定义管理员一次保存公共定价和 Provider 配置集合的请求。"""

    providers: PaymentProvidersRequest = Field(
        default_factory=PaymentProvidersRequest, description="以支付渠道为键的渠道配置对象，缺省表示不修改任何渠道"
    )
    payments: list[PaymentDisplayMethodRequest] = Field(
        default_factory=list, description="支付方式展示与独立金额范围列表"
    )
    pricing: PaymentPricingRequest = Field(default_factory=PaymentPricingRequest, description="公共充值金额和折扣配置")


class ProviderSettingsView(BaseModel):
    """定义管理员读取的脱敏 Provider 配置视图。"""

    provider: str
    gateway_url: str
    payment_methods: list[str]
    notify_url: str
    app_id: str | None = None
    partner_id: str | None = None
    seller_id: str | None = None
    merchant_private_key_configured: bool
    public_key_configured: bool | None = None
    platform_public_key_configured: bool | None = None
    api_key_configured: bool | None = None
    webhook_secret_configured: bool | None = None
    cancel_url: str | None = None


class PaymentProvidersView(BaseModel):
    """管理员查询支付配置时使用的渠道对象响应。"""

    epay: ProviderSettingsView | None = Field(default=None, description="易支付脱敏配置")
    stripe: ProviderSettingsView | None = Field(default=None, description="Stripe 脱敏配置")
    alipay_official: ProviderSettingsView | None = Field(default=None, description="支付宝官方脱敏配置")


class PaymentDisplayMethodView(BaseModel):
    """管理员查询支付配置时返回的支付方式展示项。"""

    payment_name: str = Field(description="充值页显示的支付方式名称")
    payment_channel: str = Field(description="支付渠道标识")
    payment_method: str = Field(description="原始支付方式值")
    payment_icon: str = Field(description="支付方式图标 HTTPS 地址")
    enabled: bool = Field(description="是否允许用户使用该支付方式")
    min_topup: str | None = Field(description="可选的支付方式最低充值金额")
    max_topup: str | None = Field(description="可选的支付方式最高充值金额")


class PaymentPricingView(BaseModel):
    """定义支付配置接口返回的公共快捷金额、折扣和分组倍率。"""

    min_topup: str = Field(description="公共最低充值金额")
    max_topup: str = Field(description="公共最高充值金额")
    amount_options: list[str]
    amount_discount: dict[str, str]
    group_ratios: dict[str, str]


class PaymentSettingsResponse(BaseModel):
    """定义管理员支付配置读取和保存后的响应。"""

    providers: PaymentProvidersView
    payments: list[PaymentDisplayMethodView]
    pricing: PaymentPricingView
    compliance_confirmed: bool


class PaymentTopupResponse(BaseModel):
    """定义用户充值页只读的支付方式和公共定价响应。"""

    payments: list[PaymentDisplayMethodView]
    pricing: PaymentPricingView


class PaymentComplianceConfirmRequest(BaseModel):
    """定义管理员确认当前支付条款的请求。"""

    confirmed: bool


class PaymentComplianceConfirmResponse(BaseModel):
    """定义支付合规确认成功后的审计响应。"""

    confirmed: bool
    terms_version: str
    confirmed_at: str
    confirmed_by: UUID


class PaymentQuoteResponse(BaseModel):
    """定义所有支付渠道共用的金额试算响应。"""

    payment_channel: str
    payment_method: str
    topup_amount: str
    topup_currency: Literal["CNY"]
    pay_amount: str
    pay_currency: Literal["CNY", "USD"]
    group_ratio: str
    discount: str
    exchange_rate: str | None = None


class ProviderOrderResponse(BaseModel):
    """定义 Provider 下单接口返回的订单和安全跳转动作。"""

    id: UUID = Field(description="本地充值订单主键")
    order_no: str
    status: str
    topup_amount: str
    pay_amount: str
    currency: str = "CNY"
    provider: str
    payment_method: str
    return_url: str = Field(description="本次订单使用的支付完成跳转地址")
    payment_action: dict[str, object]


class StripeProviderOrderResponse(BaseModel):
    """定义 Stripe 下单响应，明确返回人民币入账金额和美元收款金额。"""

    id: UUID = Field(description="本地充值订单主键")
    order_no: str = Field(description="本地充值订单号")
    status: str = Field(description="本地充值订单状态")
    topup_amount: str = Field(description="钱包到账人民币金额")
    topup_currency: Literal["CNY"] = Field(default="CNY", description="钱包到账金额的币种")
    pay_amount: str = Field(description="Stripe 实际收取的美元金额")
    pay_currency: Literal["USD"] = Field(default="USD", description="Stripe 实际收款币种")
    exchange_rate: str = Field(description="本次订单冻结的 1 USD 对应 CNY 汇率")
    provider: Literal["stripe"] = Field(default="stripe", description="支付服务商标识")
    payment_method: Literal["card"] = Field(default="card", description="Stripe 支付方式")
    return_url: str = Field(description="本次 Checkout 使用的支付完成跳转地址")
    payment_action: dict[str, object] = Field(description="前端跳转 Stripe Checkout 所需动作")


class TopupProviderView(BaseModel):
    """定义充值页可展示的 Provider 与已启用支付方式。"""

    provider: str
    payment_methods: list[str]


class TopupInfoResponse(BaseModel):
    """定义充值页的公共价格规则和可选支付方式响应。"""

    providers: list[TopupProviderView]
    pricing: PaymentPricingView


class OrderStatusResponse(BaseModel):
    """定义当前用户可查询的支付订单状态。"""

    order_no: str
    status: str
    topup_amount: str
    pay_amount: str
    currency: str


class PaidRechargeOrderItemResponse(BaseModel):
    """定义用户已支付充值订单列表中的单条展示数据。"""

    order_no: str = Field(description="本地业务订单号")
    topup_amount: str = Field(description="充值到账人民币金额")
    pay_amount: str = Field(description="实际支付金额")
    payment_channel: str = Field(description="支付渠道标识")
    payment_method: str = Field(description="渠道内支付方式")
    paid_at: datetime = Field(description="支付成功时间")


class PaidRechargeOrderListResponse(BaseModel):
    """定义用户分页查询已支付充值订单时的响应数据。"""

    items: list[PaidRechargeOrderItemResponse] = Field(description="当前页已支付充值订单")
    total: int = Field(description="当前用户已支付订单总数")
    page: int = Field(description="当前页码")
    page_size: int = Field(description="当前页条数")
