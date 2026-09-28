"""Stripe 支付服务，负责人民币充值订单、美元 Checkout 和回调结算。"""

import logging
import secrets
import string
from decimal import Decimal, InvalidOperation
from time import time
from uuid import UUID

from app.modules.payment.application.admin.settings import (
    is_payment_compliance_confirmed,
    payment_settings_runtime,
)
from app.modules.payment.application.errors import (
    PaymentBusinessError,
    PaymentCallbackProcessingError,
    PaymentCallbackValidationError,
    PaymentDisabledError,
    PaymentProviderUnavailableError,
)
from app.modules.payment.application.exchange_rate import ExchangeRateService, UsdChargeQuote
from app.modules.payment.application.pricing import PaymentPricingService, money_text
from app.modules.payment.application.return_url import append_order_no
from app.modules.payment.application.settlement import PaymentSettlementService
from app.modules.payment.crud.orders import PaymentCrud
from app.modules.payment.domain.config import STRIPE, StripeRuntimeConfig
from app.modules.payment.infrastructure.stripe.gateway import StripeGateway
from app.modules.wallet.model import RechargeOrder
from sqlmodel import Session

logger = logging.getLogger(__name__)
stripe_exchange_rate_service = ExchangeRateService()


class StripePaymentApplicationService:
    """提供人民币钱包充值对应的 Stripe 美元报价、下单和回调结算用例。"""

    def __init__(self, session: Session, exchange_rate_service: ExchangeRateService | None = None) -> None:
        """初始化 Stripe 支付所需的数据库会话、定价服务、汇率服务和网关。

        作用：读取当前 Stripe 配置，并准备公共人民币定价、动态 USD/CNY 汇率和 Stripe 网关。
        使用位置：Stripe HTTP 路由处理报价、下单或回调时调用。
        传入参数：session 为本次请求使用的数据库会话；exchange_rate_service 为可选汇率服务，测试时可传入固定汇率实现。
        返回参数：无；Stripe 未配置时抛出支付不可用异常。
        """
        runtime = payment_settings_runtime.get()
        config = runtime.providers.get(STRIPE) if runtime else None
        if not isinstance(config, StripeRuntimeConfig):
            raise PaymentDisabledError("Stripe 配置不可用")
        self._session = session
        self._crud = PaymentCrud(session)
        self._config = config
        self._pricing = PaymentPricingService(runtime.pricing)
        # 使用进程级服务复用 24 小时缓存；测试可注入固定汇率服务避免访问网络。
        self._exchange_rates = exchange_rate_service or stripe_exchange_rate_service
        self._gateway = StripeGateway(config)

    def create_order(self, user_id: UUID, payload: dict[str, str]) -> dict[str, object]:
        """创建人民币入账、美元收款的 Stripe Checkout 订单。

        作用：重新计算人民币定价和汇率，保存人民币 pending 订单，再创建冻结美元金额的 Stripe Checkout。
        使用位置：POST /api/payment/stripe/orders 调用。
        传入参数：user_id 为认证用户；command 为充值金额和 return_url。
        返回参数：返回本地订单 id、订单状态、金额、return_url 和 Stripe 跳转动作。
        """
        runtime = payment_settings_runtime.get()
        if runtime is None or not is_payment_compliance_confirmed(runtime):
            raise PaymentDisabledError("支付功能暂未开启")

        payment = runtime.find_payment(STRIPE, "card")
        if payment is None or not payment.enabled:
            raise PaymentDisabledError("支付方式未配置")
        if payload["payment_method"] != "card":
            raise PaymentBusinessError("Stripe 首版仅支持 card 支付方式")
        quote = self._pricing.quote(payload["amount"], payment=payment)
        # 创建订单时必须重新获取汇率，不能信任前端曾展示的报价。
        usd_charge = self._exchange_rates.quote_usd_charge(quote.pay_amount)
        # 每次创建请求都生成独立本地订单；Stripe 的远端请求仍使用订单 id 作为稳定幂等键。
        order = RechargeOrder(
            user_id=user_id,
            order_no=_new_order_no(user_id),
            amount=quote.topup_amount,
            payment_channel=STRIPE,
            payment_method="card",
            expected_pay_amount=quote.pay_amount,
        )
        # 订单号只有创建本地订单后才确定，因此在这里生成最终跳转地址。
        final_return_url = append_order_no(payload["return_url"], order.order_no)
        self._crud.add_order(order)
        self._crud.flush()

        self._session.commit()
        return self._create_checkout_response(order, usd_charge, final_return_url)

    def _create_checkout_response(
        self, order: RechargeOrder, usd_charge: UsdChargeQuote, return_url: str
    ) -> dict[str, object]:
        """为本地 pending 订单创建或恢复 Stripe Checkout 跳转地址。

        作用：使用订单主键构造稳定的 Stripe 幂等键，并将人民币金额和美元换汇结果写入 Checkout metadata。
        使用位置：新建本地订单提交成功后调用。
        传入参数：order 为已经持久化的 Stripe pending 充值订单；usd_charge 为本次订单冻结的美元美分和 USD/CNY 汇率；return_url 为 Checkout 完成或取消后的跳转地址。
        返回参数：返回订单公开字段、return_url 和 Stripe redirect 动作；Stripe 不可用时抛出 PaymentProviderUnavailableError。
        """
        try:
            # 本地订单金额始终是人民币；传给 Stripe 的只能是本次换算出的美元美分。
            remote = self._gateway.create_checkout_session(
                order.order_no,
                usd_charge.usd_cents,
                self._payment_metadata(order, usd_charge),
                f"stripe-{order.id}",
                return_url,
            )
        except Exception as exc:
            logger.exception("Stripe Checkout 创建失败 order_no=%s", order.order_no)
            raise PaymentProviderUnavailableError("Stripe 收银台暂时不可用，请稍后重试") from exc

        payment_intent = remote.get("payment_intent")
        if isinstance(payment_intent, str) and payment_intent:
            order.channel_transaction_id = payment_intent
            self._session.commit()
        return self._order_response(
            order, usd_charge, return_url, {"action_type": "redirect", "url": remote.get("url")}
        )

    def settle_callback(self, payload: bytes, signature: str) -> bool:
        """验签 Stripe Webhook 并完成成功支付的人民币钱包结算。

        作用：验证 Stripe 的美元币种和美分金额，再把已确认的人民币订单交给通用结算流程入账。
        使用位置：POST /api/payment/stripe/notify 调用。
        传入参数：payload 为原始请求体；signature 为 Stripe-Signature 请求头。
        返回参数：成功结算、重复通知或合法非支付事件返回 True。
        """
        try:
            event = self._construct_verified_event(payload, signature)
            if event.get("type") != "checkout.session.completed":
                return True
            checkout_session = event.get("data", {}).get("object", {})
            if not isinstance(checkout_session, dict):
                return True
            callback = self._build_settlement_callback(checkout_session)
            if callback is None:
                return True
            settled = PaymentSettlementService(self._session, self._crud).settle_recharge_order(
                callback, STRIPE, "card", {"paid"}, "Stripe 钱包充值"
            )
        except PaymentBusinessError:
            self._session.rollback()
            raise
        except Exception as exc:
            self._session.rollback()
            raise PaymentCallbackProcessingError("Webhook 暂时无法处理") from exc

        if settled:
            self._session.commit()
        else:
            self._session.rollback()
        return settled

    def _construct_verified_event(self, payload: bytes, signature: str) -> dict[str, object]:
        """验签并解析 Stripe Webhook，隔离网关 SDK 异常。

        作用：确认 Webhook 由 Stripe 发出且正文未被修改。
        使用位置：settle_callback 处理任何 Stripe 回调时最先调用。
        传入参数：payload 为 Stripe 原始请求字节；signature 为 Stripe-Signature 请求头。
        返回参数：返回已验签的 Stripe 事件字典；签名无效时抛出 PaymentCallbackValidationError。
        """
        try:
            return self._gateway.construct_event(payload, signature)
        except Exception as exc:
            raise PaymentCallbackValidationError("Webhook 签名无效") from exc

    @staticmethod
    def _payment_metadata(order: RechargeOrder, usd_charge: UsdChargeQuote) -> dict[str, str]:
        """生成 Stripe Checkout 中保存的订单金额和汇率快照。

        作用：冻结本笔订单的人民币应付金额、美元美分和汇率，使 Webhook 不会使用未来更新的汇率重新换算旧订单。
        使用位置：_create_checkout_response 创建 Stripe Checkout 前调用，属于远端订单参数组装步骤。
        传入参数：order 为本地充值订单；usd_charge 为本次美元换算结果。
        返回参数：返回仅含字符串的 Stripe metadata 字典。
        """
        return {
            "expected_pay_amount_cny": money_text(order.expected_pay_amount or order.amount),
            "stripe_amount_cents": str(usd_charge.usd_cents),
            "exchange_rate": str(usd_charge.usd_cny_rate),
        }

    @staticmethod
    def _build_settlement_callback(checkout_session: dict[str, object]) -> dict[str, str] | None:
        """校验 Stripe 美元收款结果并转换为公共人民币结算参数。

        作用：先验证 Stripe 的 USD 币种和美分金额，再使用已冻结的人民币金额调用现有共享结算逻辑。
        使用位置：settle_callback 验签并识别到 Checkout 完成事件后调用，属于钱包入账前的金额校验步骤。
        传入参数：checkout_session 为 Stripe Webhook 中已验签的 Checkout Session 对象。
        返回参数：支付完成且校验通过时返回共享结算所需的人民币回调字典；尚未支付时返回 None；字段或金额不合法时抛出 PaymentCallbackValidationError。
        """
        if checkout_session.get("mode") != "payment" or checkout_session.get("payment_status") != "paid":
            return None
        if checkout_session.get("currency", "").lower() != "usd":
            raise PaymentCallbackValidationError("Stripe 回调币种不是 USD")

        order_no = checkout_session.get("client_reference_id")
        payment_intent = checkout_session.get("payment_intent")
        amount_total = checkout_session.get("amount_total")
        metadata = checkout_session.get("metadata")
        if (
            not isinstance(order_no, str)
            or not isinstance(payment_intent, str)
            or not isinstance(amount_total, int)
            or not isinstance(metadata, dict)
        ):
            raise PaymentCallbackValidationError("Stripe 回调缺少必要订单字段")
        if metadata.get("order_no") != order_no:
            raise PaymentCallbackValidationError("Stripe 回调订单号不一致")

        try:
            metadata_cents = int(str(metadata["stripe_amount_cents"]))
            expected_pay_amount_cny = Decimal(str(metadata["expected_pay_amount_cny"]))
            exchange_rate = Decimal(str(metadata["exchange_rate"]))
        except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
            raise PaymentCallbackValidationError("Stripe 回调金额快照无效") from exc
        if (
            metadata_cents <= 0
            or amount_total != metadata_cents
            or not expected_pay_amount_cny.is_finite()
            or expected_pay_amount_cny <= 0
            or not exchange_rate.is_finite()
            or exchange_rate <= 0
        ):
            raise PaymentCallbackValidationError("Stripe 回调金额与订单快照不一致")

        # 共享结算只识别人民币金额；美元金额已在上方精确按美分校验完毕。
        return {
            "out_trade_no": order_no,
            "trade_no": payment_intent,
            "money": money_text(expected_pay_amount_cny),
            "trade_status": "paid",
        }

    @staticmethod
    def _order_response(
        order: RechargeOrder,
        usd_charge: UsdChargeQuote,
        return_url: str,
        action: dict[str, object],
    ) -> dict[str, object]:
        """将订单转换为 Stripe 下单接口的公开响应。

        作用：集中返回人民币钱包入账金额、美元实际支付金额和冻结汇率，避免前端混淆两种币种。
        使用位置：新建订单和幂等重试流程调用。
        传入参数：order 为充值订单；usd_charge 为美元美分和汇率快照；return_url 为本次请求的同步跳转地址；action 为支付跳转动作。
        返回参数：返回前端可消费的订单、金额、return_url 和支付动作。
        """
        return {
            "id": order.id,
            "order_no": order.order_no,
            "status": order.status.value,
            "topup_amount": money_text(order.amount),
            "topup_currency": "CNY",
            "pay_amount": ExchangeRateService.format_usd_cents(usd_charge.usd_cents),
            "pay_currency": "USD",
            "exchange_rate": str(usd_charge.usd_cny_rate),
            "provider": STRIPE,
            "payment_method": "card",
            "return_url": return_url,
            "payment_action": action,
        }


def _new_order_no(user_id: UUID) -> str:
    """生成 Stripe 本地订单号。

    作用：生成可读且长度受控的唯一候选订单号。
    使用位置：Stripe create_order 创建 RechargeOrder 时调用。
    传入参数：user_id 为当前用户 UUID。
    返回参数：返回由数据库唯一约束最终保证唯一性的订单号。
    """
    suffix = "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(6))
    return f"RO-{user_id.hex[:8].upper()}-{suffix}-{int(time())}"
