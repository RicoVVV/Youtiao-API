"""易支付服务，负责创建页面支付订单、验签通知并完成钱包入账。"""

import logging
import secrets
import string
from time import time
from uuid import UUID

from app.modules.payment.application.admin.settings import is_payment_compliance_confirmed, payment_settings_runtime
from app.modules.payment.application.errors import (
    PaymentBusinessError,
    PaymentDisabledError,
)
from app.modules.payment.application.pricing import PaymentPricingService, money_text
from app.modules.payment.application.return_url import append_order_no
from app.modules.payment.application.settlement import PaymentSettlementService
from app.modules.payment.crud.orders import PaymentCrud
from app.modules.payment.domain.config import EPAY, EpayRuntimeConfig
from app.modules.payment.infrastructure.epay.gateway import EpayPageGateway
from app.modules.wallet.model import RechargeOrder
from sqlmodel import Session

logger = logging.getLogger(__name__)


class EpayPaymentApplicationService:
    """提供易支付配置读取、页面下单和异步通知结算用例。"""

    def __init__(self, session: Session) -> None:
        """初始化易支付请求所需的数据库会话、定价服务和网关。

        作用：绑定当前请求的订单事务和进程内易支付配置。
        使用位置：易支付 HTTP 路由处理下单或回调时调用。
        传入参数：session 为 FastAPI 注入的 SQLModel 会话。
        返回参数：无；配置不存在时抛出 PaymentDisabledError。
        """
        runtime_config = payment_settings_runtime.get()
        provider_config = runtime_config.providers.get(EPAY) if runtime_config else None
        if not isinstance(provider_config, EpayRuntimeConfig):
            raise PaymentDisabledError("易支付配置不可用")
        self._session = session
        self._crud = PaymentCrud(session)
        self._config = provider_config
        self._pricing = PaymentPricingService(runtime_config.pricing)
        self._gateway = EpayPageGateway(self._config)

    def create_order(self, user_id: UUID, payload: dict[str, str]) -> dict[str, object]:
        """创建一笔易支付 pending 订单。

        作用：重新计算金额、保存本地订单并生成易支付页面表单。
        使用位置：由 POST /api/payment/epay/orders 调用。
        传入参数：user_id 为当前用户；payload 为金额、支付方式和 return_url。
        返回参数：返回本地订单 id、订单号、return_url 和已签名的页面跳转动作。
        """
        try:
            runtime = payment_settings_runtime.get()
            if runtime is None:
                raise PaymentDisabledError("支付配置不可用")
            if not is_payment_compliance_confirmed(runtime):
                raise PaymentDisabledError("支付功能暂未开启")
            if payload["payment_method"] not in self._config.payment_methods:
                raise PaymentDisabledError("支付方式未启用")
            payment = runtime.find_payment(EPAY, payload["payment_method"])
            if payment is None or not payment.enabled:
                raise PaymentDisabledError("支付方式未配置")
            quote = self._pricing.quote(payload["amount"], payment=payment)
            # 每次创建请求都生成独立订单，避免用金额或时间窗口误判用户的正常连续充值。
            order = RechargeOrder(
                user_id=user_id,
                order_no=_new_order_no(user_id),
                amount=quote.topup_amount,
                payment_channel="epay",
                payment_method=payload["payment_method"],
                expected_pay_amount=quote.pay_amount,
            )
            # 订单号只有创建本地订单后才确定，因此在这里生成最终跳转地址。
            final_return_url = append_order_no(payload["return_url"], order.order_no)
            # return_url 必须在生成签名之前传入网关，避免支付平台收到未签名的跳转地址。
            action = self._gateway.build_order_form(
                order.order_no,
                quote.pay_amount,
                f"Youtiao API 钱包充值 {money_text(order.amount)} 元",
                payload["payment_method"],
                final_return_url,
            )
            self._crud.add_order(order)
            self._crud.flush()
            self._session.commit()
            return self._order_response(order, action, final_return_url)
        except Exception:
            self._session.rollback()
            raise

    def settle_callback(self, params: dict[str, str]) -> bool:
        """验签易支付通知并完成充值结算。

        作用：将合法易支付成功通知安全转换为钱包入账，重复通知不重复入账。
        使用位置：由 GET /api/payment/epay/notify 调用。
        传入参数：params 为易支付回调字符串参数表。
        返回参数：成功或安全忽略返回 True；非法通知返回 False。
        """
        try:
            runtime = payment_settings_runtime.get()
            if runtime is None or not is_payment_compliance_confirmed(runtime):
                return False
            callback = self._gateway.verify_callback(params)
            settled = PaymentSettlementService(self._session, self._crud).settle_recharge_order(
                callback, "epay", callback["type"], {"TRADE_SUCCESS"}, "易支付支付宝充值"
            )
            if settled:
                self._session.commit()
            else:
                self._session.rollback()
            return settled
        except (PaymentBusinessError, ValueError):
            self._session.rollback()
            logger.warning("易支付回调业务校验失败")
            return False
        except Exception:
            self._session.rollback()
            raise

    @staticmethod
    def _order_response(order: RechargeOrder, action: dict[str, object], return_url: str) -> dict[str, object]:
        """转换易支付订单为公开响应。

        作用：集中控制返回字段，避免泄露商户凭据。
        使用位置：新建订单和幂等重试流程调用。
        传入参数：order 为充值订单；action 为已签名页面动作；return_url 为本次请求的同步跳转地址。
        返回参数：返回订单状态、金额、渠道、return_url 和跳转动作。
        """
        return {
            "id": order.id,
            "order_no": order.order_no,
            "status": order.status.value,
            "topup_amount": money_text(order.amount),
            "pay_amount": money_text(order.expected_pay_amount or order.amount),
            "currency": "CNY",
            "provider": "epay",
            "payment_method": order.payment_method,
            "return_url": return_url,
            "payment_action": action,
        }


def _new_order_no(user_id: UUID) -> str:
    """生成易支付本地订单号。

    作用：生成便于排障且长度受控的本地订单号。
    使用位置：易支付创建订单时调用。
    传入参数：user_id 为当前用户 UUID。
    返回参数：返回唯一性由数据库约束最终保证的订单号。
    """
    random_part = "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(6))
    return f"RO-{user_id.hex[:8].upper()}-{random_part}-{int(time())}"
