"""多支付渠道共用的充值订单锁定、幂等结算和钱包入账流程。"""

from datetime import UTC, datetime
from decimal import Decimal

from app.modules.payment.application.errors import PaymentBusinessError
from app.modules.payment.crud.orders import PaymentCrud
from app.modules.wallet.application.services import WalletApplicationService
from app.modules.wallet.model import BalanceRecordType, RechargeOrderStatus
from sqlmodel import Session


class PaymentSettlementService:
    def __init__(self, session: Session, crud: PaymentCrud) -> None:
        self._session = session
        self._crud = crud

    def settle_recharge_order(
        self,
        callback: dict[str, str],
        payment_channel: str,
        payment_method: str,
        success_statuses: set[str],
        reason: str,
    ) -> bool:
        if callback["trade_status"] not in success_statuses:
            return True
        order = self._crud.get_order_for_update(callback["out_trade_no"])
        if (
            order is None
            or order.payment_channel != payment_channel
            or order.payment_method != payment_method
            or order.expected_pay_amount is None
        ):
            raise PaymentBusinessError("支付订单不存在或支付渠道不匹配")
        if order.expected_pay_amount != Decimal(callback["money"]):
            raise PaymentBusinessError("支付回调金额与订单不一致")
        if order.status == RechargeOrderStatus.paid:
            return order.channel_transaction_id == callback["trade_no"]
        if order.status != RechargeOrderStatus.pending:
            raise PaymentBusinessError("支付订单状态不允许结算")
        transaction_order = self._crud.get_order_by_transaction_id(callback["trade_no"])
        if transaction_order is not None and transaction_order.id != order.id:
            raise PaymentBusinessError("第三方交易号已被其他订单使用")
        order.status = RechargeOrderStatus.paid
        order.channel_transaction_id = callback["trade_no"]
        order.paid_at = datetime.now(UTC)
        WalletApplicationService(self._session).grant(
            user_id=order.user_id,
            amount=order.amount,
            record_type=BalanceRecordType.recharge,
            reason=reason,
            recharge_order_id=order.id,
        )
        return True
