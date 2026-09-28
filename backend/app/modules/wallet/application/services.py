"""钱包应用服务，编排余额原子变动及用户账务记录。"""

from decimal import Decimal
from uuid import UUID, uuid4

from sqlmodel import Session

from app.core.errors import NotFoundError, PaymentRequiredError, ValidationError
from app.modules.wallet.crud.wallet_crud import WalletCrud
from app.modules.wallet.model import BalanceRecord, BalanceRecordType, RechargeOrder, Wallet


class InsufficientFundsError(PaymentRequiredError):
    """余额不足且条件扣减未命中时抛出的业务异常。"""


class WalletApplicationService:
    """提供余额、余额明细、使用记录与充值订单的事务型用例。"""

    def __init__(self, session: Session) -> None:
        """接收调用方管理的会话，不在服务内提交或回滚。"""
        self._session = session
        self._crud = WalletCrud(session)

    def get_wallet_by_user_id(self, user_id: UUID) -> Wallet | None:
        """读取用户钱包。"""
        return self._crud.get_wallet_by_user_id(user_id)

    def get_wallet_detail(self, user_id: UUID) -> dict:
        wallet = self._crud.get_wallet_by_user_id(user_id)
        if wallet is None:
            raise NotFoundError("用户钱包不存在")
        return {
            "id": str(wallet.id),
            "balance": str(wallet.balance),
            "usage": f"{self._crud.sum_settled_usage(user_id):.2f}",
            "created_at": wallet.created_at,
            "updated_at": wallet.updated_at,
        }

    def grant(
        self,
        *,
        user_id: UUID,
        amount: Decimal,
        record_type: BalanceRecordType,
        reason: str,
        operator_id: UUID | None = None,
        redemption_code_id: UUID | None = None,
        recharge_order_id: UUID | None = None,
        usage_record_id: UUID | None = None,
    ) -> BalanceRecord:
        """锁定钱包后增加余额，并同步写入一条正向余额明细。"""
        if amount <= 0:
            raise ValidationError("入账金额必须为正数")
        wallet = self._crud.get_wallet_for_update(user_id)
        if wallet is None:
            raise ValidationError("用户钱包不存在")
        before = wallet.balance
        wallet.balance += amount
        return self._crud.add_balance_record(
            BalanceRecord(
                user_id=user_id,
                change_amount=amount,
                balance_before=before,
                balance_after=wallet.balance,
                record_type=record_type,
                reason=reason,
                operator_id=operator_id,
                redemption_code_id=redemption_code_id,
                recharge_order_id=recharge_order_id,
                usage_record_id=usage_record_id,
            )
        )

    def reserve_usage_balance(self, *, user_id: UUID, usage_record_id: UUID, amount: Decimal, reason: str) -> None:
        """原子扣减余额并写入关联使用记录的扣费明细。"""
        if amount <= 0:
            raise ValidationError("扣费金额必须为正数")
        wallet = self._crud.debit_if_sufficient(user_id, amount)
        if wallet is None:
            raise InsufficientFundsError("钱包余额不足")
        self._crud.add_balance_record(
            BalanceRecord(
                user_id=user_id,
                change_amount=-amount,
                balance_before=wallet.balance + amount,
                balance_after=wallet.balance,
                record_type=BalanceRecordType.usage,
                reason=reason,
                usage_record_id=usage_record_id,
            )
        )

    def refund_usage_balance(self, *, user_id: UUID, usage_record_id: UUID, amount: Decimal, reason: str) -> None:
        """向使用记录关联的钱包预扣金额退款并写入余额明细。"""
        self.grant(
            user_id=user_id,
            amount=amount,
            record_type=BalanceRecordType.refund,
            reason=reason,
            usage_record_id=usage_record_id,
        )

    def charge_usage_balance(self, *, user_id: UUID, usage_record_id: UUID, amount: Decimal, reason: str) -> None:
        """按实际用量后付费扣减余额并写入明细，允许余额为负表示待补缴欠费。"""
        if amount <= 0:
            raise ValidationError("扣费金额必须为正数")
        wallet = self._crud.debit_unconditional(user_id, amount)
        if wallet is None:
            raise ValidationError("用户钱包不存在")
        self._crud.add_balance_record(
            BalanceRecord(
                user_id=user_id,
                change_amount=-amount,
                balance_before=wallet.balance + amount,
                balance_after=wallet.balance,
                record_type=BalanceRecordType.usage,
                reason=reason,
                usage_record_id=usage_record_id,
            )
        )

    def list_balance_records(self, user_id: UUID) -> list[BalanceRecord]:
        """读取用户自己的余额明细。"""
        return self._crud.list_balance_records(user_id)

    def list_balance_record_views(self, user_id: UUID) -> list[dict]:
        return [
            {
                "id": str(item.id),
                "record_type": item.record_type.value,
                "change_amount": str(item.change_amount),
                "balance_before": str(item.balance_before),
                "balance_after": str(item.balance_after),
                "reason": item.reason,
                "created_at": item.created_at,
            }
            for item in self._crud.list_balance_records(user_id)
        ]

    def list_recharge_order_views(self, user_id: UUID) -> list[dict]:
        return [
            {
                "id": str(item.id),
                "order_no": item.order_no,
                "amount": str(item.amount),
                "payment_channel": item.payment_channel,
                "status": item.status.value,
                "paid_at": item.paid_at,
                "created_at": item.created_at,
            }
            for item in self._crud.list_recharge_orders(user_id)
        ]

    def create_recharge_order(self, *, user_id: UUID, amount: Decimal, payment_channel: str) -> dict:
        try:
            order = RechargeOrder(
                user_id=user_id,
                order_no=f"RO-{uuid4().hex.upper()}",
                amount=amount,
                payment_channel=payment_channel,
            )
            self._crud.add_recharge_order(order)
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
        return self._recharge_order_view(order)

    @staticmethod
    def _recharge_order_view(order: RechargeOrder) -> dict:
        return {
            "id": str(order.id),
            "order_no": order.order_no,
            "amount": str(order.amount),
            "status": order.status.value,
        }
