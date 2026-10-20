"""统一解析下单目标：钱包充值金额或会员套餐，生成冻结报价与订单类型。"""

from dataclasses import dataclass
from uuid import UUID

from app.modules.membership.application.services import MembershipApplicationService
from app.modules.payment.application.pricing import PaymentPricingService, PaymentQuote, money_text
from app.modules.payment.domain.config import PaymentDisplayMethodConfig
from app.modules.wallet.model import RechargeOrderType
from sqlmodel import Session


@dataclass(frozen=True, slots=True)
class ResolvedOrderQuote:
    """一次下单或试算的服务端报价、订单类型、会员套餐与支付标题。"""

    quote: PaymentQuote
    order_type: RechargeOrderType
    membership_plan_id: UUID | None
    subject: str


class OrderQuoteResolver:
    """按请求中的 amount 或 membership_plan_id 选择充值定价或会员定价。"""

    def __init__(self, session: Session, pricing: PaymentPricingService) -> None:
        """绑定请求会话与公共充值定价服务。"""

        self._session = session
        self._pricing = pricing

    def resolve(self, user_id: UUID, payload: dict, payment: PaymentDisplayMethodConfig | None) -> ResolvedOrderQuote:
        """会员订单按套餐售价报价并校验可购买；充值订单沿用公共定价。"""

        plan_id = payload.get("membership_plan_id")
        if plan_id is not None:
            plan, level = MembershipApplicationService(self._session).ensure_purchasable(user_id, plan_id)
            return ResolvedOrderQuote(
                quote=PaymentPricingService.quote_membership(plan.price),
                order_type=RechargeOrderType.membership,
                membership_plan_id=plan.id,
                subject=f"Youtiao API 会员 {level.name}",
            )
        quote = self._pricing.quote(payload["amount"], payment=payment)
        return ResolvedOrderQuote(
            quote=quote,
            order_type=RechargeOrderType.recharge,
            membership_plan_id=None,
            subject=f"Youtiao API 钱包充值 {money_text(quote.topup_amount)} 元",
        )
