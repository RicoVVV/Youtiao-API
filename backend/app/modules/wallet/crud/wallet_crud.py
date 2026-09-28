"""钱包余额与记录的数据访问，统一封装原子余额更新和用户隔离查询。"""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, update
from sqlalchemy import select as sqlalchemy_select
from sqlmodel import Session, select

from app.modules.usage.model import UsageRecord, UsageRecordStatus
from app.modules.wallet.model import BalanceRecord, RechargeOrder, Wallet


class WalletCrud:
    """封装钱包、余额明细、使用记录及充值订单持久化操作，不提交事务。"""

    def __init__(self, session: Session) -> None:
        """绑定请求或任务共享的事务会话。"""
        self._session = session

    def create_wallet(self, user_id: UUID) -> Wallet:
        """为新用户创建零余额钱包并加入当前事务。"""
        wallet = Wallet(user_id=user_id)
        self._session.add(wallet)
        return wallet

    def get_wallet_by_user_id(self, user_id: UUID) -> Wallet | None:
        """按用户读取钱包，不修改余额。"""
        return self._session.exec(select(Wallet).where(Wallet.user_id == user_id)).first()

    def sum_settled_usage(self, user_id: UUID) -> Decimal:
        """汇总用户已结算使用记录金额。"""
        return Decimal(
            self._session.scalar(
                select(func.coalesce(func.sum(UsageRecord.amount), 0)).where(
                    UsageRecord.user_id == user_id,
                    UsageRecord.status == UsageRecordStatus.succeeded,
                )
            )
            or 0
        )

    def get_wallet_for_update(self, user_id: UUID) -> Wallet | None:
        """锁定用户钱包，供入账时可靠记录变动前后余额。"""
        return self._session.scalar(sqlalchemy_select(Wallet).where(Wallet.user_id == user_id).with_for_update())

    def debit_if_sufficient(self, user_id: UUID, amount: Decimal) -> Wallet | None:
        """条件扣减余额，余额不足时不产生任何写入。"""
        statement = (
            update(Wallet)
            .where(Wallet.user_id == user_id, Wallet.balance >= amount)
            .values(balance=Wallet.balance - amount)
            .returning(Wallet)
        )
        return self._session.execute(statement).scalar_one_or_none()

    def debit_unconditional(self, user_id: UUID, amount: Decimal) -> Wallet | None:
        """锁定钱包后无条件扣减余额，允许余额为负以支持后付费欠费。"""
        wallet = self.get_wallet_for_update(user_id)
        if wallet is None:
            return None
        wallet.balance -= amount
        return wallet

    def add_balance_record(self, record: BalanceRecord) -> BalanceRecord:
        """登记不可变余额变动明细。"""
        self._session.add(record)
        return record

    def list_balance_records(self, user_id: UUID) -> list[BalanceRecord]:
        """按时间倒序读取当前用户余额明细。"""
        return list(
            self._session.exec(
                select(BalanceRecord).where(BalanceRecord.user_id == user_id).order_by(BalanceRecord.created_at.desc())
            )
        )

    def add_recharge_order(self, order: RechargeOrder) -> RechargeOrder:
        """登记待支付在线充值订单。"""
        self._session.add(order)
        return order

    def list_recharge_orders(self, user_id: UUID) -> list[RechargeOrder]:
        """按时间倒序读取当前用户在线充值订单。"""
        return list(
            self._session.exec(
                select(RechargeOrder).where(RechargeOrder.user_id == user_id).order_by(RechargeOrder.created_at.desc())
            )
        )

    def flush(self) -> None:
        """刷新待写入实体以取得关联标识，但不提交事务。"""
        self._session.flush()
