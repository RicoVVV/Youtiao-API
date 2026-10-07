"""支付宝官方支付服务，负责创建订单、生成支付表单和处理回调结算。"""

import logging
import secrets
import string
from time import time
from uuid import UUID

from app.core.config import get_settings
from app.modules.payment.application.admin.settings import is_payment_compliance_confirmed, payment_settings_runtime
from app.modules.payment.application.errors import (
    PaymentBusinessError,
    PaymentDisabledError,
    PaymentOrderNotFoundError,
)
from app.modules.payment.application.pricing import PaymentPricingService, money_text
from app.modules.payment.application.return_url import append_order_no
from app.modules.payment.application.settlement import PaymentSettlementService
from app.modules.payment.crud.orders import PaymentCrud
from app.modules.payment.domain.config import ALIPAY_OFFICIAL, AlipayOfficialRuntimeConfig
from app.modules.payment.infrastructure.alipay.gateway import AlipayPageGateway
from app.modules.wallet.model import RechargeOrder
from sqlmodel import Session

logger = logging.getLogger(__name__)


class PaymentApplicationService:
    """提供支付配置、报价、创建订单、回调结算和订单查询的应用用例。"""

    def __init__(self, session: Session) -> None:
        """初始化当前请求所需的支付 CRUD、定价服务和支付宝适配器。

        作用：确保同一请求的订单读取、写入和钱包入账共用数据库会话。
        使用位置：支付路由为每个请求创建一个服务实例。
        传入参数：session 为 FastAPI 注入的 SQLModel 会话。
        返回参数：无。
        """

        self._session = session
        self._settings = get_settings()
        self._crud = PaymentCrud(session)
        runtime_config = payment_settings_runtime.get()
        if runtime_config is None:
            raise PaymentDisabledError("支付配置不可用")
        self._pricing = PaymentPricingService(runtime_config.pricing)
        provider_config = runtime_config.providers.get(ALIPAY_OFFICIAL)
        self._alipay_config = provider_config if isinstance(provider_config, AlipayOfficialRuntimeConfig) else None
        self._gateway = AlipayPageGateway(self._alipay_config) if self._alipay_config else None

    def get_topup_info(self) -> dict[str, object]:
        """获取充值页面展示用的当前支付配置。

        作用：只返回已启用支付方式和金额配置，不创建订单也不泄露商户资料。
        使用位置：由 GET /api/payment/topup-info 调用。
        传入参数：无。
        返回参数：返回 payments 和 pricing 组成的充值配置字典。
        """

        runtime = payment_settings_runtime.get()
        if runtime is None:
            raise PaymentDisabledError("支付配置不可用")
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
            for payment in runtime.payments
            if payment.enabled and self._is_compliance_confirmed()
        ]
        info = self._pricing.topup_info(enabled=True)
        return {
            "payments": payments,
            "pricing": {
                "min_topup": info["min_topup"],
                "max_topup": info["max_topup"],
                "amount_options": info["amount_options"],
                "amount_discount": info["amount_discount"],
                "group_ratios": {"default": "1.00"},
            },
        }

    def create_alipay_order(self, user_id: UUID, payload: dict[str, str]) -> dict[str, object]:
        """创建一笔支付宝官方 pending 订单。

        作用：服务端重新计算金额、冻结订单数据并生成网关表单，防止客户端篡改价格。
        使用位置：由 POST /api/payment/alipay/orders 调用。
        传入参数：user_id 为 JWT 当前用户；payload 为充值金额和 return_url。
        返回参数：返回本地订单 id、订单状态、return_url 和已签名的支付宝表单参数。
        """

        try:
            response = self._create_alipay_order(user_id, payload)
            self._session.commit()
            return response
        except Exception:
            # 建单失败时不保留半成品订单，事务边界由应用服务统一管理。
            self._session.rollback()
            raise

    def settle_alipay_callback(self, params: dict[str, str]) -> bool:
        """验签支付宝通知并在同一事务内完成订单状态变更和钱包入账。

        作用：这是唯一能将在线充值订单入账的钱包入口，重复通知不会重复加余额。
        使用位置：由 POST /api/payment/alipay/notify 调用。
        传入参数：params 为回调的查询参数或表单参数。
        返回参数：成功或已安全忽略的通知返回 True；需要网关重试时返回 False。
        """

        try:
            settled = self._settle_alipay_callback(params)
            if settled:
                self._session.commit()
            else:
                self._session.rollback()
            return settled
        except PaymentBusinessError:
            self._session.rollback()
            logger.warning("支付宝 回调业务校验失败")
            return False
        except ValueError:
            self._session.rollback()
            logger.warning("支付宝 回调验签或字段校验失败")
            return False
        except Exception:
            self._session.rollback()
            raise

    def _create_alipay_order(self, user_id: UUID, payload: dict[str, str]) -> dict[str, object]:
        """构造支付宝订单和支付表单，但不决定请求事务结果。

        作用：集中建单业务规则，使公开方法只负责建单事务边界。
        使用位置：仅由 create_alipay_order 在提交事务前调用。
        传入参数：user_id 为 JWT 当前用户；payload 为充值金额和 return_url。
        返回参数：返回本地订单 id、订单状态、return_url 和已签名的支付宝表单参数。
        """

        self._require_payment_enabled()
        if payload["payment_method"] != "page_pay":
            raise PaymentBusinessError("支付宝官方不支持该支付方式")
        payment = payment_settings_runtime.get().find_payment(ALIPAY_OFFICIAL, "page_pay")
        if payment is None or not payment.enabled:
            raise PaymentDisabledError("支付方式未配置")
        quote = self._pricing.quote(payload["amount"], payment=payment)
        order = RechargeOrder(
            user_id=user_id,
            order_no=_new_order_no(user_id),
            amount=quote.topup_amount,
            payment_channel="alipay_official",
            payment_method="page_pay",
            expected_pay_amount=quote.pay_amount,
        )
        # 订单号只有创建本地订单后才确定，因此在这里生成最终跳转地址。
        final_return_url = append_order_no(payload["return_url"], order.order_no)
        # 先完成表单构造，再写入订单，避免留下无法提交给网关的 pending 订单。
        # return_url 必须先写入表单参数，才能纳入支付宝 RSA2 签名。
        payment_action = self._gateway.build_order_form(
            order.order_no, quote.pay_amount, f"Youtiao API 钱包充值 {money_text(order.amount)} 元", final_return_url
        )
        self._crud.add_order(order)
        self._crud.flush()
        return self._order_response(order, payment_action, final_return_url)

    def _settle_alipay_callback(self, params: dict[str, str]) -> bool:
        """执行 支付宝 回调的验签和入账业务规则，但不决定事务提交或回滚。

        作用：让公开回调方法统一控制事务，本方法只处理支付状态机和钱包入账。
        使用位置：仅由 settle_alipay_callback 在事务提交前调用。
        传入参数：params 为回调的查询参数或表单参数。
        返回参数：成功或已安全忽略的通知返回 True；应拒绝的通知返回 False 或抛出业务异常。
        """

        if not self._alipay_config or not self._gateway or not self._is_compliance_confirmed():
            return False
        callback = self._gateway.verify_callback(params)
        # 非支付成功状态已验签但不改变订单，按协议确认接收以避免无意义重试。
        if callback["trade_status"] not in {"TRADE_SUCCESS", "TRADE_FINISHED"}:
            return True
        # 支付宝字段名为 total_amount，共享结算流程统一使用 money 字段。
        callback["money"] = callback["total_amount"]
        return PaymentSettlementService(self._session, self._crud).settle_recharge_order(
            callback, "alipay_official", "page_pay", {"TRADE_SUCCESS", "TRADE_FINISHED"}, "支付宝官方充值"
        )

    def get_order(self, user_id: UUID, order_no: str) -> dict[str, str]:
        """读取当前用户自己的支付订单状态。

        作用：为支付完成页轮询提供归属隔离后的订单信息。
        使用位置：由 GET /api/payment/orders/{order_no} 调用。
        传入参数：user_id 为 JWT 当前用户；order_no 为待查询的本地订单号。
        返回参数：返回可公开展示的订单字段；订单不存在时抛出 PaymentBusinessError。
        """

        order = self._crud.get_order_for_user(user_id, order_no)
        if order is None:
            raise PaymentOrderNotFoundError("订单不存在")
        return {
            "order_no": order.order_no,
            "status": order.status.value,
            "topup_amount": money_text(order.amount),
            "pay_amount": money_text(order.expected_pay_amount or order.amount),
            "currency": "CNY",
        }

    def _require_payment_enabled(self) -> None:
        """确认当前部署允许创建真实支付订单。

        作用：在建单前阻止关闭支付开关的环境生成无效网关订单。
        使用位置：由 create_alipay_order 的第一步调用。
        传入参数：无。
        返回参数：无；支付关闭时抛出 PaymentDisabledError。
        """

        if not self._alipay_config or not self._is_compliance_confirmed():
            raise PaymentDisabledError("支付功能暂未开启")

    def _is_compliance_confirmed(self) -> bool:
        """读取当前快照判断支付条款是否确认有效。"""
        config = payment_settings_runtime.get()
        return bool(config and is_payment_compliance_confirmed(config))

    @staticmethod
    def _order_response(order: RechargeOrder, payment_action: dict[str, object], return_url: str) -> dict[str, object]:
        """转换支付订单为建单接口响应。

        作用：集中控制公开订单字段，避免返回内部商户配置。
        使用位置：由新建订单和幂等重试流程共同调用。
        传入参数：order 为充值订单；payment_action 为已签名支付表单动作；return_url 为本次请求的同步跳转地址。
        返回参数：返回符合支付宝建单响应契约的订单、return_url 和表单动作。
        """

        return {
            "id": order.id,
            "order_no": order.order_no,
            "status": order.status.value,
            "topup_amount": money_text(order.amount),
            "pay_amount": money_text(order.expected_pay_amount or order.amount),
            "currency": "CNY",
            "provider": "alipay_official",
            "payment_method": "page_pay",
            "return_url": return_url,
            "payment_action": payment_action,
        }


def _new_order_no(user_id: UUID) -> str:
    """生成参考 new-api 语义并缩短后的本地支付订单号。

    作用：保留用户标识、随机段和时间段，便于排障，同时控制订单号长度。
    使用位置：由 _create_alipay_order 创建 pending 订单时调用。
    传入参数：user_id 为当前付款用户的 UUID。
    返回参数：返回格式为 RO-{用户UUID前8位}-{6位随机串}-{Unix秒时间戳} 的订单号。
    """

    user_short_id = user_id.hex[:8].upper()
    random_part = "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(6))
    return f"RO-{user_short_id}-{random_part}-{int(time())}"
