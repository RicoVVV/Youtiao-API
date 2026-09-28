"""Stripe 网关适配器，负责创建美元 Checkout 并写入订单汇率快照。"""

from typing import Any

import stripe
from app.modules.payment.domain.config import StripeRuntimeConfig


class StripeGateway:
    """封装 Stripe Checkout Session 创建和 Webhook 验签。"""

    def __init__(self, config: StripeRuntimeConfig) -> None:
        """初始化 Stripe 客户端配置。

        作用：绑定一份已校验的 Stripe 运行时快照。
        使用位置：Stripe 应用服务创建网关时调用。
        传入参数：config 为当前 Stripe Provider 配置。
        返回参数：无。
        """
        self._config = config

    def create_checkout_session(
        self,
        order_no: str,
        usd_cents: int,
        payment_metadata: dict[str, str],
        idempotency_key: str,
        return_url: str,
    ) -> dict[str, Any]:
        """创建一次性 Checkout Session。

        作用：把本地人民币订单转换为 Stripe 美元托管收银台链接，并冻结本次换汇结果。
        使用位置：Stripe 下单流程提交本地 pending 订单后调用。
        传入参数：order_no 为本地订单号；usd_cents 为 Stripe 实收的美元美分；payment_metadata 为服务端生成的人民币金额、汇率和美元美分快照；idempotency_key 为稳定远端幂等键；return_url 为 Checkout 完成或取消后的跳转地址。
        返回参数：返回 Stripe Session 的公开 URL、PaymentIntent 和状态字段。
        """
        stripe.api_key = self._config.api_key
        session = stripe.checkout.Session.create(
            mode="payment",
            # 当前 Stripe 账户默认启用 Managed Payments；关闭本次请求的托管选择，才能固定首版只使用银行卡。
            managed_payments={"enabled": False},
            payment_method_types=["card"],
            client_reference_id=order_no,
            # Stripe 的 USD 金额必须以美分整数传入，不能传入浮点美元金额。
            line_items=[
                {
                    "price_data": {
                        "currency": "usd",
                        "product_data": {"name": "Youtiao API 钱包充值"},
                        "unit_amount": usd_cents,
                    },
                    "quantity": 1,
                }
            ],
            # Stripe 不使用前端签名表单，直接把本次请求地址交给 Checkout 处理支付完成和取消跳转。
            success_url=return_url,
            cancel_url=return_url,
            # metadata 是本笔交易冻结的汇率和金额快照，Webhook 必须用它校验美元实收金额。
            metadata={"order_no": order_no, **payment_metadata},
            idempotency_key=idempotency_key,
        )
        return {
            "id": session.id,
            "url": session.url,
            "payment_intent": session.payment_intent,
            "payment_status": session.payment_status,
            "mode": session.mode,
            "livemode": session.livemode,
        }

    def construct_event(self, payload: bytes, signature: str) -> dict[str, Any]:
        """使用 Stripe 签名密钥验证并解析 Webhook。

        作用：确认回调来自 Stripe 且原始内容未被篡改。
        使用位置：Webhook 路由读取原始请求体后调用。
        传入参数：payload 为原始请求体；signature 为 Stripe-Signature 请求头。
        返回参数：返回验签后的事件字典；验签失败由 SDK 抛出异常。
        """
        event = stripe.Webhook.construct_event(payload, signature, self._config.webhook_secret)
        return dict(event)
