"""支付配置应用服务，负责 Provider 配置校验、加密持久化和运行时快照发布。"""

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from urllib.parse import urlparse
from uuid import UUID

from app.core.config import Settings
from app.core.errors import ApplicationError, ValidationError, error_context
from app.modules.payment.crud.settings import PaymentSettingsCrud
from app.modules.payment.domain.config import (
    ALIPAY_OFFICIAL,
    EPAY,
    STRIPE,
    AlipayOfficialRuntimeConfig,
    EpayRuntimeConfig,
    PaymentDisplayMethodConfig,
    PaymentPricingConfig,
    PaymentProviderRuntimeConfig,
    PaymentRuntimeConfig,
    StripeRuntimeConfig,
)
from app.modules.payment.infrastructure.epay.keys import load_merchant_private_key, load_platform_public_key
from app.modules.payment.runtime.settings_cache import PaymentSettingsRuntime
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from sqlmodel import Session

payment_settings_runtime = PaymentSettingsRuntime()
CURRENT_COMPLIANCE_TERMS_VERSION = "2026-09"

# 管理员尚未配置渠道时，仍向管理端返回稳定的支付方式枚举。
# 这些值同时也是各 Provider 当前支持的支付方式约束。
DEFAULT_PAYMENT_METHODS: dict[str, tuple[str, ...]] = {
    ALIPAY_OFFICIAL: ("page_pay",),
    EPAY: ("alipay", "wxpay"),
    STRIPE: ("card",),
}


class InvalidPaymentSettingsError(ApplicationError):
    """表示管理员提交的支付配置不满足业务校验规则。"""


class PaymentConfigEncryptionError(ApplicationError):
    """表示支付敏感配置无法安全加密或解密。"""


class PaymentComplianceError(ApplicationError):
    """表示管理员支付合规确认不满足业务规则。"""


@dataclass(frozen=True, slots=True)
class ProviderSettingsCommand:
    """保存 Provider 通用配置和未加密敏感字段的应用层命令。"""

    provider: str
    gateway_url: str
    return_url: str
    payment_methods: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AlipayOfficialSettingsCommand(ProviderSettingsCommand):
    """保存支付宝官方专属配置的应用层命令。"""

    app_id: str
    merchant_private_key: str | None
    public_key: str | None
    seller_id: str | None


@dataclass(frozen=True, slots=True)
class EpaySettingsCommand(ProviderSettingsCommand):
    """保存易支付专属配置的应用层命令。"""

    partner_id: str
    merchant_private_key: str | None
    platform_public_key: str | None


@dataclass(frozen=True, slots=True)
class StripeSettingsCommand(ProviderSettingsCommand):
    """保存 Stripe 管理配置的应用层命令。"""

    api_key: str | None
    webhook_secret: str | None
    cancel_url: str
    mode: str
    currency: str


@dataclass(frozen=True, slots=True)
class PaymentDisplayMethodCommand:
    """保存支付方式展示信息和独立充值金额范围的应用层命令。"""

    payment_name: str
    payment_channel: str
    payment_method: str
    payment_icon: str
    enabled: bool
    min_topup: str | None
    max_topup: str | None


@dataclass(frozen=True, slots=True)
class PaymentSettingsCommand:
    """保存管理员支付配置集合和公共定价规则的应用层命令。"""

    providers: tuple[ProviderSettingsCommand, ...]
    payments: tuple[PaymentDisplayMethodCommand, ...]
    min_topup: str
    max_topup: str
    amount_options: list[str]
    amount_discount: dict[str, str]
    group_ratios: dict[str, str]


def is_payment_compliance_confirmed(config: PaymentRuntimeConfig) -> bool:
    """判断当前快照的支付合规确认是否仍对应现行条款。

    作用：统一决定展示、下单和回调是否可执行。
    使用位置：支付应用服务在进入支付业务前调用。
    传入参数：config 为当前支付运行时快照。
    返回参数：确认且条款版本匹配时返回 True。
    """
    return config.compliance_confirmed and config.compliance_terms_version == CURRENT_COMPLIANCE_TERMS_VERSION


def _is_https_url(value: str) -> bool:
    """判断支付回调地址是否为合法的 HTTPS 地址。"""

    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc)


class PaymentSettingsService:
    """从 options 加载并更新支付配置，确保数据库与内存快照一致。"""

    def __init__(self, session: Session, settings: Settings) -> None:
        """绑定本次配置操作的数据库会话和加密配置。"""
        self._session = session
        self._settings = settings
        self._crud = PaymentSettingsCrud(session)

    def load_from_database(self) -> PaymentRuntimeConfig:
        """从新命名空间配置键构造完整运行时快照。

        作用：启动及刷新时将持久化数据转换为类型化 Provider 配置。
        使用位置：PaymentSettingsRuntimeManager.refresh 和管理员读取配置时调用。
        传入参数：无。
        返回参数：返回已校验的完整快照；配置不合法时抛出 InvalidPaymentSettingsError。
        """
        values = self._crud.get_values()

        def get(key: str, default: str = "") -> str:
            """读取配置键，不存在时返回默认值。"""
            return values.get(key, default)

        pricing = self._load_pricing(get)
        callback_base_url = self._settings.payment_callback_base_url.rstrip("/")
        providers = self._load_providers(get, callback_base_url)
        payments = self._load_display_methods(get)
        return PaymentRuntimeConfig(
            pricing,
            providers,
            get("Payment.ComplianceConfirmed").lower() == "true",
            get("Payment.ComplianceTermsVersion"),
            self._parse_datetime(get("Payment.ComplianceConfirmedAt")),
            self._parse_uuid(get("Payment.ComplianceConfirmedBy")),
            get("Payment.ComplianceConfirmedIP") or None,
            payments,
        )

    def update_admin_settings(self, payload: dict[str, object]) -> dict[str, object]:
        """校验并保存 Provider 集合，在提交成功后原子发布新快照。

        作用：保证敏感值按 Provider 复用或加密，失败时数据库和旧快照均保持不变。
        使用位置：PUT /api/admin/payment/settings 调用。
        传入参数：command 为已通过 HTTP 结构校验的管理员配置命令。
        返回参数：返回不含明文密钥的管理员配置视图。
        """
        try:
            command = self._settings_command(payload)
            current = payment_settings_runtime.get() or self.load_from_database()
            self._validate_provider_commands(command.providers)
            payments = self._display_methods_from_command(command)
            pricing = self._pricing_from_command(command, payments)
            providers = self._build_providers(command, current.providers)
            self._validate_display_methods(payments, providers, pricing)
            candidate = PaymentRuntimeConfig(
                pricing,
                providers,
                current.compliance_confirmed,
                current.compliance_terms_version,
                current.compliance_confirmed_at,
                current.compliance_confirmed_by,
                current.compliance_confirmed_ip,
                payments,
            )
            values = self._public_values(candidate, command.providers)
            values.update(self._encrypted_values(command.providers))
            self._crud.upsert_values(values)
            self._session.commit()
            payment_settings_runtime.replace(candidate)
            return self._admin_projection(candidate)
        except PaymentConfigEncryptionError:
            self._session.rollback()
            raise
        except (TypeError, ValueError) as exc:
            self._session.rollback()
            raise InvalidPaymentSettingsError(str(exc), **error_context(exc)) from exc

    def get_admin_settings(self) -> dict[str, object]:
        """返回当前支付配置的脱敏管理员视图。"""
        return self._admin_projection(payment_settings_runtime.get() or self.load_from_database())

    @staticmethod
    def _settings_command(payload: dict[str, object]) -> PaymentSettingsCommand:
        providers_data = payload.get("providers")
        pricing_data = payload.get("pricing")
        payments_data = payload.get("payments", [])
        if (
            not isinstance(providers_data, dict)
            or not isinstance(pricing_data, dict)
            or not isinstance(payments_data, list)
        ):
            raise InvalidPaymentSettingsError("支付配置格式无效")
        providers: list[ProviderSettingsCommand] = []
        for provider in (ALIPAY_OFFICIAL, EPAY, STRIPE):
            item = providers_data.get(provider)
            if item is None:
                continue
            if not isinstance(item, dict):
                raise InvalidPaymentSettingsError("支付服务商配置格式无效")
            common = {
                "provider": provider,
                "gateway_url": str(item.get("gateway_url", "")),
                "return_url": str(item.get("return_url", "")),
                "payment_methods": tuple(str(method) for method in item.get("payment_methods", [])),
            }
            if provider == ALIPAY_OFFICIAL:
                providers.append(
                    AlipayOfficialSettingsCommand(
                        **common,
                        app_id=str(item.get("app_id", "")),
                        merchant_private_key=item.get("merchant_private_key"),
                        public_key=item.get("public_key"),
                        seller_id=item.get("seller_id"),
                    )
                )
            elif provider == EPAY:
                providers.append(
                    EpaySettingsCommand(
                        **common,
                        partner_id=str(item.get("partner_id", "")),
                        merchant_private_key=item.get("merchant_private_key"),
                        platform_public_key=item.get("platform_public_key"),
                    )
                )
            else:
                providers.append(
                    StripeSettingsCommand(
                        **common,
                        api_key=item.get("api_key"),
                        webhook_secret=item.get("webhook_secret"),
                        cancel_url=str(item.get("cancel_url", "")),
                        mode=str(item.get("mode", "test")),
                        currency=str(item.get("currency", "USD")),
                    )
                )
        payments: list[PaymentDisplayMethodCommand] = []
        for item in payments_data:
            if not isinstance(item, dict):
                raise InvalidPaymentSettingsError("支付方式配置格式无效")
            payments.append(
                PaymentDisplayMethodCommand(
                    payment_name=str(item["payment_name"]),
                    payment_channel=str(item["payment_channel"]),
                    payment_method=str(item["payment_method"]),
                    payment_icon=str(item.get("payment_icon", "")),
                    enabled=bool(item.get("enabled", False)),
                    min_topup=item.get("min_topup"),
                    max_topup=item.get("max_topup"),
                )
            )
        return PaymentSettingsCommand(
            providers=tuple(providers),
            payments=tuple(payments),
            min_topup=str(pricing_data["min_topup"]),
            max_topup=str(pricing_data["max_topup"]),
            amount_options=[str(value) for value in pricing_data["amount_options"]],
            amount_discount={str(key): str(value) for key, value in pricing_data["amount_discount"].items()},
            group_ratios={str(key): str(value) for key, value in pricing_data["group_ratios"].items()},
        )

    def confirm_current_terms(self, confirmed: bool, user_id: UUID, client_ip: str | None) -> dict[str, object]:
        """确认当前支付条款并发布新的合规运行时快照。"""
        if not confirmed:
            raise PaymentComplianceError("必须明确确认当前支付条款")
        try:
            return self.save_compliance_confirmation(user_id, client_ip)
        except Exception as exc:
            raise PaymentComplianceError("支付合规确认保存失败") from exc

    def save_compliance_confirmation(self, user_id: UUID, client_ip: str | None) -> dict[str, object]:
        """保存管理员对当前支付条款的确认，并在提交成功后刷新快照。

        作用：持久化确认状态、条款版本和审计信息，使支付 Provider 的合规门禁立即生效。
        使用位置：confirm_current_terms 在管理员确认接口中调用。
        传入参数：user_id 为确认条款的管理员 UUID；client_ip 为确认请求的客户端 IP，可为空。
        返回参数：返回确认状态、当前条款版本、确认时间和确认管理员，不包含支付配置。
        """
        confirmed_at = datetime.now(UTC)
        try:
            self._crud.upsert_values(
                {
                    "Payment.ComplianceConfirmed": "true",
                    "Payment.ComplianceTermsVersion": CURRENT_COMPLIANCE_TERMS_VERSION,
                    "Payment.ComplianceConfirmedAt": confirmed_at.isoformat(),
                    "Payment.ComplianceConfirmedBy": str(user_id),
                    "Payment.ComplianceConfirmedIP": client_ip or "",
                }
            )
            # 提交成功后才发布快照，防止内存状态领先于数据库。
            self._session.commit()
            payment_settings_runtime.replace(self.load_from_database())
        except Exception:
            self._session.rollback()
            raise
        return {
            "confirmed": True,
            "terms_version": CURRENT_COMPLIANCE_TERMS_VERSION,
            "confirmed_at": confirmed_at.isoformat(),
            "confirmed_by": user_id,
        }

    def _load_pricing(self, get) -> PaymentPricingConfig:
        """读取并校验公共定价配置，供加载快照流程调用。"""
        config = PaymentPricingConfig(
            Decimal(get("Payment.Pricing.MinTopUp", "0.01")),
            Decimal(get("Payment.Pricing.MaxTopUp", "10000.00")),
            tuple(
                Decimal(value)
                for value in json.loads(
                    get(
                        "Payment.Pricing.AmountOptions",
                        '["100.00", "200.00", "300.00", "500.00", "1000.00"]',
                    )
                )
            ),
            {
                Decimal(key): Decimal(value)
                for key, value in json.loads(
                    get(
                        "Payment.Pricing.AmountDiscount",
                        '{"100.00": "0.99", "200.00": "0.98", "300.00": "0.97", "500.00": "0.96", "1000.00": "0.95"}',
                    )
                ).items()
            },
            {
                key: Decimal(value)
                for key, value in json.loads(get("Payment.Pricing.GroupRatios", '{"default": "1.00"}')).items()
            },
        )
        self.validate_pricing_config(config)
        return config

    def _load_providers(self, get, callback_base_url: str) -> dict[str, PaymentProviderRuntimeConfig]:
        """按 Provider 标识读取配置并构造运行时支付快照。

        作用：从 options 表读取各支付渠道的公开配置和已加密凭据，生成本进程使用的类型化运行时配置。
        使用位置：load_from_database 刷新支付配置缓存时调用，属于支付渠道配置加载步骤。
        传入参数：get 为按键读取 options 值的函数；callback_base_url 为统一拼接各渠道 Webhook 地址的 HTTPS 基础地址。
        返回参数：返回以支付渠道标识为键的运行时配置字典；配置不合法时抛出 ValueError。
        """
        providers: dict[str, PaymentProviderRuntimeConfig] = {}
        for provider in (ALIPAY_OFFICIAL, EPAY, STRIPE):
            prefix = self._provider_prefix(provider)
            registered = get(f"{prefix}.Registered").lower() == "true"
            default_gateway = "https://api.stripe.com" if provider == STRIPE else ""
            configured_methods = tuple(json.loads(get(f"{prefix}.PaymentMethods", "[]"))) if registered else ()
            common = dict(
                provider=provider,
                gateway_url=get(f"{prefix}.GatewayURL", default_gateway) or default_gateway,
                callback_url=self._callback_url(callback_base_url, provider),
                return_url=get(f"{prefix}.ReturnURL"),
                payment_methods=configured_methods if registered else (),
            )
            if provider == ALIPAY_OFFICIAL:
                config = AlipayOfficialRuntimeConfig(
                    **common,
                    app_id=get(f"{prefix}.AppID"),
                    private_key=self._decrypt_or_empty(get(f"{prefix}.MerchantPrivateKeyCiphertext")),
                    public_key=self._decrypt_or_empty(get(f"{prefix}.PublicKeyCiphertext")),
                    seller_id=get(f"{prefix}.SellerID") or None,
                )
            elif provider == EPAY:
                config = EpayRuntimeConfig(
                    **common,
                    partner_id=get(f"{prefix}.PartnerID"),
                    private_key=self._decrypt_or_empty(get(f"{prefix}.MerchantPrivateKeyCiphertext")),
                    platform_public_key=self._decrypt_or_empty(get(f"{prefix}.PlatformPublicKeyCiphertext")),
                )
            else:
                config = StripeRuntimeConfig(
                    **common,
                    api_key=self._decrypt_or_empty(get(f"{prefix}.APIKeyCiphertext")),
                    webhook_secret=self._decrypt_or_empty(get(f"{prefix}.WebhookSecretCiphertext")),
                    cancel_url=get(f"{prefix}.CancelURL"),
                    mode=get(f"{prefix}.Mode", "test"),
                    currency=get(f"{prefix}.Currency", "USD"),
                )
            self.validate_provider_config(config)
            providers[provider] = config
        return providers

    def _load_display_methods(self, get) -> tuple[PaymentDisplayMethodConfig, ...]:
        """从配置表读取支付方式展示配置。

        作用：把持久化的 JSON 配置转换为运行时使用的不可变支付方式配置。
        使用位置：应用启动、定时刷新和管理员查询支付配置时调用。
        传入参数：get 为按键读取配置值的函数。
        返回参数：返回支付方式配置元组；旧数据缺少 enabled 时从旧渠道开关兼容读取。
        """
        return tuple(
            PaymentDisplayMethodConfig(
                payment_name=item["payment_name"],
                payment_channel=item["payment_channel"],
                payment_method=item["payment_method"],
                payment_icon=item["payment_icon"],
                enabled=item.get(
                    "enabled",
                    get(f"{self._provider_prefix(item['payment_channel'])}.Enabled", "false").lower() == "true",
                ),
                min_topup=Decimal(item["min_topup"]) if item["min_topup"] is not None else None,
                max_topup=Decimal(item["max_topup"]) if item["max_topup"] is not None else None,
            )
            for item in json.loads(get("Payment.DisplayMethods", "[]"))
        )

    @staticmethod
    def _display_methods_from_command(
        command: PaymentSettingsCommand,
    ) -> tuple[PaymentDisplayMethodConfig, ...]:
        """把管理员提交的支付方式配置转换为运行时金额类型。

        作用：在应用层统一使用 Decimal，避免金额在后续校验和计算中出现浮点误差。
        使用位置：管理员更新支付配置事务开始时调用。
        传入参数：command 为接口映射得到的完整支付配置命令。
        返回参数：返回包含 Decimal 金额的支付方式配置元组。
        """
        return tuple(
            PaymentDisplayMethodConfig(
                payment_name=item.payment_name,
                payment_channel=item.payment_channel,
                payment_method=item.payment_method,
                payment_icon=item.payment_icon,
                enabled=item.enabled,
                min_topup=Decimal(item.min_topup) if item.min_topup is not None else None,
                max_topup=Decimal(item.max_topup) if item.max_topup is not None else None,
            )
            for item in command.payments
        )

    def _pricing_from_command(
        self, command: PaymentSettingsCommand, payments: tuple[PaymentDisplayMethodConfig, ...]
    ) -> PaymentPricingConfig:
        """从支付方式范围和公共折扣规则构造全局定价配置。

        作用：保留现有快捷金额与折扣计算能力，并以所有方式的总范围校验快捷金额。
        使用位置：管理员更新支付配置时，在保存前构造候选运行时配置。
        传入参数：command 为管理员配置命令；payments 为已转换金额类型的支付方式配置。
        返回参数：返回校验通过的公共定价配置；无效数据时抛出 ValueError。
        """
        config = PaymentPricingConfig(
            min_topup=Decimal(command.min_topup),
            max_topup=Decimal(command.max_topup),
            amount_options=tuple(Decimal(value) for value in command.amount_options),
            amount_discount={Decimal(key): Decimal(value) for key, value in command.amount_discount.items()},
            group_ratios={key: Decimal(value) for key, value in command.group_ratios.items()},
        )
        self.validate_pricing_config(config)
        return config

    def _build_providers(self, command: PaymentSettingsCommand, old) -> dict[str, PaymentProviderRuntimeConfig]:
        """将命令转换为 Provider 快照，并只复用相同 Provider 的旧密钥。"""
        providers: dict[str, PaymentProviderRuntimeConfig] = dict(old)
        for item in command.providers:
            previous = old.get(item.provider)
            common = dict(
                provider=item.provider,
                gateway_url=item.gateway_url,
                callback_url=self._callback_url(self._settings.payment_callback_base_url, item.provider),
                return_url=item.return_url,
                payment_methods=item.payment_methods,
            )
            if isinstance(item, AlipayOfficialSettingsCommand):
                prior = previous if isinstance(previous, AlipayOfficialRuntimeConfig) else None
                config = AlipayOfficialRuntimeConfig(
                    **common,
                    app_id=item.app_id,
                    private_key=item.merchant_private_key or (prior.private_key if prior else ""),
                    public_key=item.public_key or (prior.public_key if prior else ""),
                    seller_id=item.seller_id,
                )
            elif isinstance(item, EpaySettingsCommand):
                prior = previous if isinstance(previous, EpayRuntimeConfig) else None
                config = EpayRuntimeConfig(
                    **common,
                    partner_id=item.partner_id,
                    private_key=item.merchant_private_key or (prior.private_key if prior else ""),
                    platform_public_key=item.platform_public_key or (prior.platform_public_key if prior else ""),
                )
            elif isinstance(item, StripeSettingsCommand):
                prior = previous if isinstance(previous, StripeRuntimeConfig) else None
                config = StripeRuntimeConfig(
                    **common,
                    api_key=item.api_key or (prior.api_key if prior else ""),
                    webhook_secret=item.webhook_secret or (prior.webhook_secret if prior else ""),
                    cancel_url=item.cancel_url,
                    mode=item.mode,
                    currency=item.currency,
                )
            else:
                raise InvalidPaymentSettingsError("不支持的支付服务商配置")
            self.validate_provider_config(config)
            providers[item.provider] = config
        return providers

    @staticmethod
    def _validate_provider_commands(items: tuple[ProviderSettingsCommand, ...]) -> None:
        """校验 Provider 标识和 Provider 内支付方式均不存在重复。"""
        providers = [item.provider for item in items]
        if len(providers) != len(set(providers)):
            raise InvalidPaymentSettingsError("支付服务商不能重复")
        for item in items:
            if item.provider not in {ALIPAY_OFFICIAL, EPAY, STRIPE}:
                raise InvalidPaymentSettingsError("不支持的支付服务商")
            if len(item.payment_methods) != len(set(item.payment_methods)):
                raise InvalidPaymentSettingsError("支付方式不能为空且不能重复")

    @staticmethod
    def _validate_display_methods(
        payments: tuple[PaymentDisplayMethodConfig, ...],
        providers: dict[str, PaymentProviderRuntimeConfig],
        pricing: PaymentPricingConfig,
    ) -> None:
        """校验支付方式展示项能唯一对应已配置渠道且金额和图标合法。

        作用：确保管理员配置的支付方式可真正下单，且查询接口能准确返回渠道方式组合枚举。
        使用位置：管理员更新支付配置时，在构建 Provider 配置后、写入数据库前调用。
        传入参数：payments 为待保存的支付方式配置；providers 为完整的候选渠道配置；pricing 为公共默认金额范围。
        返回参数：无；校验失败时抛出 InvalidPaymentSettingsError 并阻止保存。
        """
        channel_methods = [(item.payment_channel, item.payment_method) for item in payments]
        if len(channel_methods) != len(set(channel_methods)):
            raise InvalidPaymentSettingsError("支付渠道与支付方式组合不能重复")
        for payment in payments:
            effective_min = payment.min_topup or pricing.min_topup
            effective_max = payment.max_topup or pricing.max_topup
            # 支付方式未单独配置的边界继承公共范围后，仍必须是有效区间。
            if effective_min <= 0 or effective_max < effective_min:
                raise InvalidPaymentSettingsError("支付方式充值金额范围无效")
            if payment.payment_icon:
                icon_url = urlparse(payment.payment_icon)
                if icon_url.scheme != "https" or not icon_url.netloc:
                    raise InvalidPaymentSettingsError("支付方式图标必须使用 HTTPS 地址")
            provider = providers.get(payment.payment_channel)
            if provider is None or payment.payment_method not in provider.payment_methods:
                raise InvalidPaymentSettingsError("支付方式未在指定支付渠道中启用")

    @staticmethod
    def validate_provider_config(config: PaymentProviderRuntimeConfig) -> None:
        """校验支付渠道的公共地址、专属凭据、方式和收款币种。

        作用：阻止不完整或不安全的已配置支付渠道进入运行时缓存，确保下单和回调可以使用同一份有效配置。
        使用位置：加载数据库配置和管理员保存新配置时调用，属于支付配置发布前校验步骤。
        传入参数：config 为待发布的渠道运行时配置，可能是支付宝、易支付或 Stripe 的类型化配置。
        返回参数：无；配置无效时抛出 ValueError，调用方不会发布该配置。
        """
        if not config.payment_methods:
            return
        if not _is_https_url(config.gateway_url):
            raise ValidationError(
                f"{config.provider}网关地址必须使用 HTTPS 地址",
                code="payment.gateway_url_https_required",
                params={"provider": config.provider},
            )
        if not _is_https_url(config.callback_url):
            raise ValidationError(
                f"{config.provider}回调地址必须使用 HTTPS 地址",
                code="payment.callback_url_https_required",
                params={"provider": config.provider},
            )
        if config.return_url and not _is_https_url(config.return_url):
            raise ValidationError(
                f"{config.provider}返回地址必须使用 HTTPS 地址",
                code="payment.return_url_https_required",
                params={"provider": config.provider},
            )
        if isinstance(config, AlipayOfficialRuntimeConfig):
            if (
                config.payment_methods != ("page_pay",)
                or not config.app_id.strip()
                or not config.private_key
                or not config.public_key
            ):
                raise ValueError("支付宝官方必须配置 AppID、密钥和 page_pay 支付方式")
            keys = config.private_key, config.public_key
        elif isinstance(config, EpayRuntimeConfig):
            if not config.partner_id.strip() or not config.private_key or not config.platform_public_key:
                raise ValueError("易支付必须配置商户 ID 和密钥")
            keys = config.private_key, config.platform_public_key
        elif isinstance(config, StripeRuntimeConfig):
            if (
                config.currency != "USD"
                or config.mode not in {"test", "live"}
                or not config.api_key
                or not config.webhook_secret
            ):
                raise ValueError("Stripe 必须配置 API Key、Webhook Secret、test/live 模式和 USD 币种")
            if config.cancel_url:
                parsed_cancel = urlparse(config.cancel_url)
                if parsed_cancel.scheme != "https" or not parsed_cancel.netloc:
                    raise ValueError("Stripe 取消地址必须使用 HTTPS 地址")
            if config.payment_methods != ("card",):
                raise ValueError("Stripe 首版仅支持 card 支付方式")
            keys = ()
        else:
            raise ValueError("不支持的支付服务商配置")
        try:
            if isinstance(config, StripeRuntimeConfig):
                return
            if isinstance(config, EpayRuntimeConfig):
                load_merchant_private_key(keys[0])
                load_platform_public_key(keys[1])
            else:
                serialization.load_pem_private_key(keys[0].encode(), password=None)
                serialization.load_pem_public_key(keys[1].encode())
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                f"{config.provider} RSA 密钥格式无效",
                code="payment.rsa_key_format_invalid",
                params={"provider": config.provider},
            ) from exc

    @staticmethod
    def validate_pricing_config(config: PaymentPricingConfig) -> None:
        """校验公共金额范围、优惠和用户分组倍率。"""
        if config.min_topup <= 0 or config.max_topup < config.min_topup or not config.amount_options:
            raise ValueError("充值金额范围无效")
        if not config.group_ratios or "default" not in config.group_ratios:
            raise ValueError("充值倍率必须包含 default 分组")
        for amount in config.amount_options:
            if amount < config.min_topup or amount > config.max_topup or amount.as_tuple().exponent < -2:
                raise ValueError("快捷充值金额必须在范围内且最多两位小数")
        for value in [*config.group_ratios.values(), *config.amount_discount.values()]:
            if not value.is_finite() or value <= 0:
                raise ValueError("充值折扣和倍率必须为有限正数")

    def _public_values(
        self, config: PaymentRuntimeConfig, providers: tuple[ProviderSettingsCommand, ...]
    ) -> dict[str, str]:
        """生成公共和非敏感 Provider 配置的 options 键值。"""
        values = {
            "Payment.Pricing.MinTopUp": str(config.pricing.min_topup),
            "Payment.Pricing.MaxTopUp": str(config.pricing.max_topup),
            "Payment.Pricing.AmountOptions": json.dumps([str(value) for value in config.pricing.amount_options]),
            "Payment.Pricing.AmountDiscount": json.dumps(
                {str(key): str(value) for key, value in config.pricing.amount_discount.items()}
            ),
            "Payment.Pricing.GroupRatios": json.dumps(
                {key: str(value) for key, value in config.pricing.group_ratios.items()}
            ),
            "Payment.DisplayMethods": json.dumps(
                [
                    {
                        "payment_name": item.payment_name,
                        "payment_channel": item.payment_channel,
                        "payment_method": item.payment_method,
                        "payment_icon": item.payment_icon,
                        "min_topup": str(item.min_topup) if item.min_topup is not None else None,
                        "max_topup": str(item.max_topup) if item.max_topup is not None else None,
                        "enabled": item.enabled,
                    }
                    for item in config.payments
                ]
            ),
        }
        for item in providers:
            prefix = self._provider_prefix(item.provider)
            values.update(
                {
                    f"{prefix}.Registered": "true",
                    f"{prefix}.GatewayURL": item.gateway_url,
                    f"{prefix}.ReturnURL": item.return_url,
                    f"{prefix}.PaymentMethods": json.dumps(item.payment_methods),
                }
            )
            if isinstance(item, AlipayOfficialSettingsCommand):
                values.update({f"{prefix}.AppID": item.app_id, f"{prefix}.SellerID": item.seller_id or ""})
            elif isinstance(item, EpaySettingsCommand):
                values[f"{prefix}.PartnerID"] = item.partner_id
            else:
                values.update(
                    {
                        f"{prefix}.Mode": item.mode,
                        f"{prefix}.Currency": item.currency,
                        f"{prefix}.CancelURL": item.cancel_url,
                    }
                )
        return values

    def _encrypted_values(self, providers: tuple[ProviderSettingsCommand, ...]) -> dict[str, str]:
        """仅加密本次提交的 Provider 敏感字段，空字段表示保留已有密钥。"""
        values: dict[str, str] = {}
        for item in providers:
            prefix = self._provider_prefix(item.provider)
            if isinstance(item, AlipayOfficialSettingsCommand):
                sensitive = (
                    ("MerchantPrivateKeyCiphertext", item.merchant_private_key),
                    ("PublicKeyCiphertext", item.public_key),
                )
            elif isinstance(item, EpaySettingsCommand):
                sensitive = (
                    ("MerchantPrivateKeyCiphertext", item.merchant_private_key),
                    ("PlatformPublicKeyCiphertext", item.platform_public_key),
                )
            else:
                sensitive = (("APIKeyCiphertext", item.api_key), ("WebhookSecretCiphertext", item.webhook_secret))
            for key, value in sensitive:
                if value:
                    values[f"{prefix}.{key}"] = self._encrypt(value)
        return values

    @staticmethod
    def _provider_prefix(provider: str) -> str:
        """返回 Provider 在 options 表使用的稳定命名空间前缀。"""
        return f"Payment.Provider.{'AlipayOfficial' if provider == ALIPAY_OFFICIAL else 'Epay' if provider == EPAY else 'Stripe'}"

    @staticmethod
    def _callback_url(callback_base_url: str, provider: str) -> str:
        """生成与实际 FastAPI 路由一致的支付平台回调地址。

        作用：统一配置保存和配置读取时的回调地址，避免支付平台请求旧路径导致无法入账。
        使用位置：加载渠道配置和管理员保存渠道配置时调用。
        传入参数：callback_base_url 为服务对外 HTTPS 基础地址；provider 为支付渠道标识。
        返回参数：返回该渠道应配置给第三方支付平台的完整回调地址。
        """
        route_provider = "alipay-official" if provider == ALIPAY_OFFICIAL else provider
        return f"{callback_base_url.rstrip('/')}/api/payments/{route_provider}/notify"

    def _encrypt(self, plaintext: str) -> str:
        """使用配置的 Fernet 密钥加密单个敏感字段。"""
        if not self._settings.payment_config_encryption_key:
            raise PaymentConfigEncryptionError("支付加密服务不可用")
        return Fernet(self._settings.payment_config_encryption_key.encode()).encrypt(plaintext.encode()).decode()

    def _decrypt_or_empty(self, ciphertext: str) -> str:
        """解密已存密文；空值代表该 Provider 尚未配置对应凭据。"""
        return self._decrypt(ciphertext) if ciphertext else ""

    def _decrypt(self, ciphertext: str) -> str:
        """解密 options 中的 Provider 敏感字段。"""
        if not self._settings.payment_config_encryption_key:
            raise PaymentConfigEncryptionError("支付加密服务不可用")
        try:
            return Fernet(self._settings.payment_config_encryption_key.encode()).decrypt(ciphertext.encode()).decode()
        except Exception as exc:
            raise PaymentConfigEncryptionError("支付配置密文无法解密") from exc

    @staticmethod
    def _parse_datetime(value: str) -> datetime | None:
        """解析可选合规确认时间，空值保持为 None。"""
        return datetime.fromisoformat(value) if value else None

    @staticmethod
    def _parse_uuid(value: str) -> UUID | None:
        """解析可选合规确认管理员标识，空值保持为 None。"""
        return UUID(value) if value else None

    @staticmethod
    def _admin_projection(config: PaymentRuntimeConfig) -> dict[str, object]:
        """将运行时支付配置转换为管理员可读取的脱敏对象。

        作用：返回文档约定的渠道对象、支付方式列表和公共折扣配置，避免暴露任何明文密钥。
        使用位置：管理员读取配置和更新配置成功后调用。
        传入参数：config 为已校验并发布的支付运行时快照。
        返回参数：返回可由 PaymentSettingsResponse 序列化的字典。
        """
        providers: dict[str, dict[str, object]] = {}
        for provider in config.providers.values():
            item: dict[str, object] = {
                "provider": provider.provider,
                "gateway_url": provider.gateway_url,
                "payment_methods": list(provider.payment_methods),
                "notify_url": provider.callback_url,
            }
            if isinstance(provider, AlipayOfficialRuntimeConfig):
                item.update(
                    {
                        "app_id": provider.app_id,
                        "seller_id": provider.seller_id,
                        "merchant_private_key_configured": bool(provider.private_key),
                        "public_key_configured": bool(provider.public_key),
                    }
                )
            elif isinstance(provider, EpayRuntimeConfig):
                item.update(
                    {
                        "partner_id": provider.partner_id,
                        "merchant_private_key_configured": bool(provider.private_key),
                        "platform_public_key_configured": bool(provider.platform_public_key),
                    }
                )
            elif isinstance(provider, StripeRuntimeConfig):
                item.update(
                    {
                        "merchant_private_key_configured": False,
                        "api_key_configured": bool(provider.api_key),
                        "webhook_secret_configured": bool(provider.webhook_secret),
                        "cancel_url": provider.cancel_url,
                    }
                )
            providers[provider.provider] = item
        payments = [
            {
                "payment_name": payment.payment_name,
                "payment_channel": payment.payment_channel,
                "payment_method": payment.payment_method,
                "payment_icon": payment.payment_icon,
                "enabled": payment.enabled,
                "min_topup": str(payment.min_topup) if payment.min_topup is not None else None,
                "max_topup": str(payment.max_topup) if payment.max_topup is not None else None,
            }
            for payment in config.payments
        ]
        return {
            "providers": providers,
            "payments": payments,
            "pricing": {
                "min_topup": str(config.pricing.min_topup),
                "max_topup": str(config.pricing.max_topup),
                "amount_options": [str(value) for value in config.pricing.amount_options],
                "amount_discount": {str(key): str(value) for key, value in config.pricing.amount_discount.items()},
                "group_ratios": {key: str(value) for key, value in config.pricing.group_ratios.items()},
            },
            "compliance_confirmed": is_payment_compliance_confirmed(config),
        }


class PaymentSettingsRuntimeManager:
    """协调配置表加载和内存快照发布。"""

    def __init__(self, session_factory, settings: Settings) -> None:
        """保存刷新支付配置所需的会话工厂和应用配置。"""
        self._session_factory = session_factory
        self._settings = settings

    def refresh(self) -> PaymentRuntimeConfig:
        """从数据库读取完整配置并在成功后原子替换快照。"""
        with self._session_factory() as session:
            config = PaymentSettingsService(session, self._settings).load_from_database()
        payment_settings_runtime.replace(config)
        return config

    def load_initial(self) -> None:
        """应用启动时尝试加载配置，失败时保持支付功能关闭。"""
        try:
            self.refresh()
        except Exception:
            logging.getLogger(__name__).exception("支付配置初次加载失败，支付保持关闭")

    def get(self) -> PaymentRuntimeConfig | None:
        """返回当前内存快照，不触发数据库读取。"""
        return payment_settings_runtime.get()
