"""用户已支付充值订单查询服务，负责将订单数据转换为安全的列表响应。"""

from uuid import UUID

from app.modules.payment.application.pricing import money_text
from app.modules.payment.crud.orders import PaymentCrud
from sqlmodel import Session


class PaymentOrderQueryService:
    """编排用户已支付充值订单的只读查询，不依赖支付渠道运行时配置。"""

    def __init__(self, session: Session) -> None:
        """初始化订单查询所需的数据访问对象。

        作用：让当前 HTTP 请求使用注入的数据库会话查询订单。
        使用位置：由用户支付路由处理已支付订单列表请求时创建。
        传入参数：session 为 FastAPI 注入的当前数据库会话。
        返回参数：无；创建可复用的 PaymentCrud 实例。
        """

        self._crud = PaymentCrud(session)

    def list_paid_orders(self, user_id: UUID, page: int, page_size: int) -> dict[str, object]:
        """返回当前用户分页后的已支付充值订单。

        作用：读取已支付订单并转换为前端需要的订单号、金额、支付渠道、方式和支付时间。
        使用位置：由 GET /api/payments/orders/paid 路由调用，是用户查询历史充值订单的业务步骤。
        传入参数：user_id 为当前 JWT 对应的用户标识；page 为从 1 开始的页码；page_size 为每页返回数量。
        返回参数：返回包含 items、total、page 和 page_size 的字典，供 FastAPI 按响应 DTO 序列化。
        """

        total, orders = self._crud.list_paid_orders_for_user(user_id, page, page_size)
        return {
            "items": [
                {
                    "order_no": order.order_no,
                    "topup_amount": money_text(order.amount),
                    "pay_amount": money_text(order.expected_pay_amount or order.amount),
                    "payment_channel": order.payment_channel,
                    "payment_method": order.payment_method,
                    "paid_at": order.paid_at,
                }
                for order in orders
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
