"""管理员支付流水查询与导出服务，负责时间范围校验和订单视图组装。"""

from datetime import UTC, datetime, timedelta

from app.core.errors import ValidationError
from app.modules.payment.application.pricing import money_text
from app.modules.payment.crud.orders import PaymentCrud
from app.modules.wallet.model import RechargeOrder
from sqlmodel import Session

# 管理端支付流水查询的最大时间跨度，避免一次拉取过量流水。
MAX_QUERY_SPAN_DAYS = 366


class AdminPaymentOrderService:
    """编排管理员已支付充值订单的只读查询与导出数据组装。"""

    def __init__(self, session: Session) -> None:
        """绑定当前请求的数据库会话并创建订单数据访问对象。

        作用：让管理端支付流水查询使用注入的会话读取充值订单。
        使用位置：由管理员支付路由处理列表与导出请求时创建。
        传入参数：session 为 FastAPI 注入的当前数据库会话。
        返回参数：无。
        """

        self._crud = PaymentCrud(session)

    def list_orders(
        self,
        *,
        start_at: datetime,
        end_at: datetime,
        username: str | None,
        payment_channel: str | None,
        order_no: str | None,
        page: int,
        page_size: int,
    ) -> dict[str, object]:
        """返回管理端分页后的已支付充值订单流水。

        作用：校验时间范围后读取已支付订单并转换为管理端展示字段。
        使用位置：由 GET /api/admin/payments/orders/list 路由调用。
        传入参数：start_at 与 end_at 为支付时间闭区间；username、payment_channel、order_no 为可选精确筛选；page 与 page_size 控制分页。
        返回参数：返回包含 items、total、page 和 page_size 的字典，供 FastAPI 按响应 DTO 序列化。
        """

        start_at, end_at = self._normalize_range(start_at, end_at)
        total, rows = self._crud.list_paid_orders_for_admin(
            start_at=start_at,
            end_at=end_at,
            username=username,
            payment_channel=payment_channel,
            order_no=order_no,
            page=page,
            page_size=page_size,
        )
        return {
            "items": [self._item_view(order, name) for order, name in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def list_export_rows(
        self,
        *,
        start_at: datetime,
        end_at: datetime,
        username: str | None,
        payment_channel: str | None,
        order_no: str | None,
    ) -> list[dict[str, object]]:
        """返回符合筛选条件的全部已支付充值订单视图，供导出文件使用。

        作用：与列表共用时间范围校验和视图结构，但不分页。
        使用位置：由 GET /api/admin/payments/orders/export 路由调用。
        传入参数：start_at 与 end_at 为支付时间闭区间；username、payment_channel、order_no 为可选精确筛选。
        返回参数：返回订单视图字典列表，字段与列表项一致。
        """

        start_at, end_at = self._normalize_range(start_at, end_at)
        rows = self._crud.list_paid_orders_for_export(
            start_at=start_at,
            end_at=end_at,
            username=username,
            payment_channel=payment_channel,
            order_no=order_no,
        )
        return [self._item_view(order, name) for order, name in rows]

    @staticmethod
    def _normalize_range(start_at: datetime, end_at: datetime) -> tuple[datetime, datetime]:
        """将查询时间统一为 UTC 并校验区间合法性与最大跨度。

        作用：避免无时区时间与数据库 timestamptz 比较产生歧义，并阻止过大批量导出。
        使用位置：由列表与导出用例在访问数据层前调用。
        传入参数：start_at 与 end_at 为请求传入的支付时间闭区间。
        返回参数：返回归一化后的 UTC 起止时间；区间倒置或跨度超限时抛出校验错误。
        """

        normalized_start = start_at if start_at.tzinfo is not None else start_at.replace(tzinfo=UTC)
        normalized_end = end_at if end_at.tzinfo is not None else end_at.replace(tzinfo=UTC)
        normalized_start = normalized_start.astimezone(UTC)
        normalized_end = normalized_end.astimezone(UTC)
        if normalized_start > normalized_end:
            raise ValidationError("开始时间不能晚于结束时间")
        if normalized_end - normalized_start > timedelta(days=MAX_QUERY_SPAN_DAYS):
            raise ValidationError(
                f"查询时间跨度不能超过 {MAX_QUERY_SPAN_DAYS} 天",
                code="payment.order_query_span_exceeded",
                params={"days": MAX_QUERY_SPAN_DAYS},
            )
        return normalized_start, normalized_end

    @staticmethod
    def _item_view(order: RechargeOrder, username: str) -> dict[str, object]:
        """将充值订单转换为管理端支付流水展示字段。

        作用：统一列表与导出的字段结构与金额格式，避免泄露内部敏感配置。
        使用位置：由列表与导出用例组装每条流水时调用。
        传入参数：order 为已支付充值订单实体；username 为订单归属用户名。
        返回参数：返回订单号、用户、金额、渠道、交易号和时间的展示字典。
        """

        return {
            "order_no": order.order_no,
            "user_id": str(order.user_id),
            "username": username,
            "topup_amount": money_text(order.amount),
            "pay_amount": money_text(order.expected_pay_amount or order.amount),
            "payment_channel": order.payment_channel,
            "payment_method": order.payment_method,
            "channel_transaction_id": order.channel_transaction_id,
            "status": order.status.value,
            "created_at": order.created_at,
            "paid_at": order.paid_at,
        }
