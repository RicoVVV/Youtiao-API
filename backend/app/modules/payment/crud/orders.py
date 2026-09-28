"""支付订单数据访问层，集中处理订单保存、归属查询和支付回调行锁。"""

from uuid import UUID

from app.modules.wallet.model import RechargeOrder, RechargeOrderStatus
from sqlalchemy import func
from sqlalchemy import select as sqlalchemy_select
from sqlmodel import Session, select


class PaymentCrud:
    """封装充值订单的支付专用查询，调用方负责事务提交和回滚。"""

    def __init__(self, session: Session) -> None:
        """绑定当前请求的数据库会话。

        作用：让同一支付流程的订单更新和钱包入账共享一个事务。
        使用位置：由 PaymentApplicationService 创建并复用。
        传入参数：session 为 FastAPI 注入的 SQLModel 会话。
        返回参数：无。
        """

        self._session = session

    def add_order(self, order: RechargeOrder) -> RechargeOrder:
        """将新建的 pending 充值订单加入当前事务。

        作用：持久化服务端冻结的入账金额和实付金额。
        使用位置：由创建支付宝订单流程调用。
        传入参数：order 为待保存的充值订单实体。
        返回参数：返回同一个已加入会话的订单实体。
        """

        self._session.add(order)
        return order

    def get_order_for_user(self, user_id: UUID, order_no: str) -> RechargeOrder | None:
        """按当前用户和订单号查询订单状态。

        作用：在查询接口中直接完成归属过滤，避免越权读取他人订单。
        使用位置：由 GET /api/payment/orders/{order_no} 调用。
        传入参数：user_id 为 JWT 中的当前用户；order_no 为本地订单号。
        返回参数：返回属于该用户的订单；不存在时返回 None。
        """

        return self._session.exec(
            select(RechargeOrder).where(RechargeOrder.user_id == user_id, RechargeOrder.order_no == order_no)
        ).first()

    def list_paid_orders_for_user(self, user_id: UUID, page: int, page_size: int) -> tuple[int, list[RechargeOrder]]:
        """分页查询当前用户已完成支付的充值订单。

        作用：在数据访问层完成用户归属、已支付状态过滤、总数统计和稳定排序，避免应用层直接拼接数据库查询。
        使用位置：由 PaymentOrderQueryService 在处理用户已支付订单列表请求时调用。
        传入参数：user_id 为当前 JWT 对应的用户标识；page 为从 1 开始的页码；page_size 为每页返回数量。
        返回参数：返回订单总数和当前页充值订单列表，供应用层转换为接口响应。
        """

        # 查询条件固定包含当前用户和 paid 状态，确保不会泄露其他用户或未完成支付的订单。
        conditions = (RechargeOrder.user_id == user_id, RechargeOrder.status == RechargeOrderStatus.paid)
        total = int(self._session.scalar(sqlalchemy_select(func.count(RechargeOrder.id)).where(*conditions)) or 0)
        orders = list(
            self._session.exec(
                select(RechargeOrder)
                .where(*conditions)
                # 支付时间相同时再按主键倒序，保证翻页时列表顺序稳定。
                .order_by(RechargeOrder.paid_at.desc(), RechargeOrder.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        return total, orders

    def get_order_for_update(self, order_no: str) -> RechargeOrder | None:
        """按订单号锁定订单，串行化同一订单的并发支付回调。

        作用：保证 pending 到 paid 的状态切换与钱包入账只会执行一次。
        使用位置：由支付宝异步回调结算流程在事务内调用。
        传入参数：order_no 为支付宝回传的 out_trade_no。
        返回参数：返回已锁定订单；不存在时返回 None。
        """

        return self._session.scalar(
            sqlalchemy_select(RechargeOrder).where(RechargeOrder.order_no == order_no).with_for_update()
        )

    def get_order_by_transaction_id(self, transaction_id: str) -> RechargeOrder | None:
        """查询第三方交易号是否已归属另一笔订单。

        作用：防止同一支付宝交易号被错误结算到多个本地订单。
        使用位置：由支付宝异步回调结算流程在写入交易号前调用。
        传入参数：transaction_id 为支付宝回传的 trade_no。
        返回参数：返回占用该交易号的订单；不存在时返回 None。
        """

        return self._session.exec(
            select(RechargeOrder).where(RechargeOrder.channel_transaction_id == transaction_id)
        ).first()

    def flush(self) -> None:
        """刷新当前会话以触发唯一约束检查，但不提交事务。

        作用：让创建订单流程在提交前获得数据库生成或校验后的订单状态。
        使用位置：由各支付渠道创建订单并加入会话后调用。
        传入参数：无。
        返回参数：无。
        """

        self._session.flush()
