"""支付定价服务，统一解析配置并计算用户充值金额对应的实际付款金额。"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.modules.payment.application.errors import PaymentAmountInvalidError
from app.modules.payment.domain.config import PaymentDisplayMethodConfig, PaymentPricingConfig

MONEY_QUANTUM = Decimal("0.01")


@dataclass(frozen=True, slots=True)
class PaymentQuote:
    """一次服务端报价结果，供报价接口和创建订单共用。"""

    topup_amount: Decimal
    pay_amount: Decimal
    group_ratio: Decimal
    discount: Decimal


class PaymentPricingService:
    """根据支付宝运行时配置计算订单金额，不信任客户端提交的价格。"""

    def __init__(self, settings: PaymentPricingConfig) -> None:
        """读取并保存本次请求使用的支付价格配置。

        作用：保存 options 快照中的 Decimal 价格配置，供所有定价入口复用。
        使用位置：由 PaymentApplicationService 初始化，在报价和建单时调用。
        传入参数：settings 为当前进程缓存的运行配置。
        返回参数：无。
        """

        self._min_topup = settings.min_topup
        self._max_topup = settings.max_topup
        self._amount_options = list(settings.amount_options)
        self._amount_discount = settings.amount_discount
        self._group_ratios = settings.group_ratios

    def quote(
        self,
        amount_text: str,
        group_name: str = "default",
        payment: PaymentDisplayMethodConfig | None = None,
    ) -> PaymentQuote:
        """校验充值金额并计算实际支付金额。

        作用：执行金额边界、默认用户分组倍率和精确档位折扣规则。
        使用位置：由报价接口与创建订单接口共同调用，保证两个入口计算一致。
        传入参数：amount_text 为客户端传入的金额字符串；group_name 为用户价格分组，第一期固定 default；payment 为可选的支付方式独立金额范围。
        返回参数：返回包含入账金额、实付金额、倍率和折扣的 PaymentQuote。
        """

        amount = Decimal(amount_text)
        # 金额语义是用户希望入账的钱包金额，不能由前端传入实际付款价格。
        min_topup = payment.min_topup if payment and payment.min_topup is not None else self._min_topup
        max_topup = payment.max_topup if payment and payment.max_topup is not None else self._max_topup
        # 下单时传入支付方式配置，确保管理员设置的方式级金额范围真正生效。
        if amount < min_topup or amount > max_topup:
            raise PaymentAmountInvalidError("充值金额不在允许范围内")
        ratio = self._group_ratios.get(group_name, self._group_ratios["default"])
        discount = self._amount_discount.get(amount, Decimal("1"))
        pay_amount = (amount * ratio * discount).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
        if pay_amount < MONEY_QUANTUM:
            raise PaymentAmountInvalidError("实际支付金额不能小于 0.01 元")
        return PaymentQuote(topup_amount=amount, pay_amount=pay_amount, group_ratio=ratio, discount=discount)

    def topup_info(self, enabled: bool) -> dict[str, object]:
        """构造充值页面需要的展示配置。

        作用：将内部 Decimal 配置转为接口约定的字符串和整数列表。
        使用位置：由 GET /api/payment/topup-info 调用。
        传入参数：enabled 表示支付商户配置是否完整且允许建单。
        返回参数：返回前端展示用的充值配置字典。
        """

        return {
            "enabled": enabled,
            "payment_providers": [
                {"provider": "alipay_official", "display_name": "支付宝", "payment_method": "page_pay"}
            ],
            "currency": "CNY",
            "min_topup": money_text(self._min_topup),
            "max_topup": money_text(self._max_topup),
            "amount_options": [money_text(option) for option in self._amount_options],
            "amount_discount": {
                money_text(amount): money_text(discount) for amount, discount in self._amount_discount.items()
            },
            "allow_custom_amount": True,
        }


def money_text(value: Decimal) -> str:
    """将金额按两位小数输出为接口字符串。

    作用：避免 Decimal 在 JSON 中被序列化为浮点数，统一支付金额展示格式。
    使用位置：由支付定价、订单响应和网关参数构造调用。
    传入参数：value 为需展示或提交网关的十进制金额。
    返回参数：返回固定两位小数的金额字符串。
    """

    return str(value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP))
