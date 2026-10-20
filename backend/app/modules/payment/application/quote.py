"""统一支付金额试算服务，负责公共定价和各支付渠道专属金额处理。"""

from uuid import UUID

from app.modules.payment.application.admin.settings import is_payment_compliance_confirmed, payment_settings_runtime
from app.modules.payment.application.errors import PaymentDisabledError
from app.modules.payment.application.order_quote import OrderQuoteResolver
from app.modules.payment.application.payment.stripe import stripe_exchange_rate_service
from app.modules.payment.application.pricing import PaymentPricingService, money_text
from app.modules.payment.domain.config import STRIPE
from sqlmodel import Session


class PaymentQuoteApplicationService:
    """编排支付宝、易支付和 Stripe 的统一金额试算流程。"""

    def __init__(self, session: Session) -> None:
        """绑定请求会话，供会员套餐试算读取套餐与用户会员状态。"""

        self._session = session

    def quote(
        self,
        user_id: UUID,
        amount: str | None,
        membership_plan_id: UUID | None,
        payment_channel: str,
        payment_method: str,
    ) -> dict[str, str | None]:
        """计算指定支付方式的最终展示报价。

        作用：统一校验支付状态、查找启用方式、执行充值或会员定价，并在 Stripe 渠道追加美元换算。
        使用位置：由 POST /api/payments/quote 路由调用，属于创建订单前的金额展示步骤。
        传入参数：user_id 为当前用户；amount 为钱包充值金额；membership_plan_id 为会员套餐，二者只提供一个；
        payment_channel 为支付渠道；payment_method 为渠道内支付方式。
        返回参数：返回钱包到账金额、实际支付金额、币种、倍率、折扣和 Stripe 汇率组成的报价字典。
        """
        runtime = payment_settings_runtime.get()
        if runtime is None or not is_payment_compliance_confirmed(runtime):
            raise PaymentDisabledError("支付功能暂未开启")

        provider = runtime.providers.get(payment_channel)
        payment = runtime.find_payment(payment_channel, payment_method)
        if provider is None or payment is None or not payment.enabled:
            raise PaymentDisabledError("支付方式未配置")

        # 充值订单继续由公共定价负责金额范围、分组倍率和折扣；会员订单按套餐售价报价。
        pricing = PaymentPricingService(runtime.pricing)
        quote = (
            OrderQuoteResolver(self._session, pricing)
            .resolve(user_id, {"amount": amount, "membership_plan_id": membership_plan_id}, payment)
            .quote
        )
        result: dict[str, str | None] = {
            "payment_channel": payment_channel,
            "payment_method": payment_method,
            "topup_amount": money_text(quote.topup_amount),
            "topup_currency": "CNY",
            "group_ratio": money_text(quote.group_ratio),
            "discount": money_text(quote.discount),
            "exchange_rate": None,
        }

        if payment_channel == STRIPE:
            # Stripe 收款币种是 USD；汇率服务继续使用现有缓存和向上取整到美分的规则。
            usd_charge = stripe_exchange_rate_service.quote_usd_charge(quote.pay_amount)
            result["pay_amount"] = stripe_exchange_rate_service.format_usd_cents(usd_charge.usd_cents)
            result["pay_currency"] = "USD"
            result["exchange_rate"] = str(usd_charge.usd_cny_rate)
        else:
            result["pay_amount"] = money_text(quote.pay_amount)
            result["pay_currency"] = "CNY"

        return result
