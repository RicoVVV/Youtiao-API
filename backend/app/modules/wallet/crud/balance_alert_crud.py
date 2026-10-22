"""余额预警的数据访问，封装提醒状态读取与去重写入。"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, update
from sqlalchemy.dialects.postgresql import insert
from sqlmodel import Session

from app.modules.wallet.model import BalanceAlertState


class BalanceAlertCrud:
    """封装余额预警状态查询与写入，不提交事务。"""

    def __init__(self, session: Session) -> None:
        """绑定调用方提供的事务会话。"""

        self._session = session

    def get_alert_state(self, user_id: UUID) -> BalanceAlertState | None:
        """读取用户的余额预警状态；从未提醒过时返回空。"""

        return self._session.get(BalanceAlertState, user_id)

    def mark_alerted(self, *, user_id: UUID, balance: Decimal, alerted_at: datetime) -> None:
        """登记提醒已发送，避免同一低余额周期重复发信。"""

        statement = (
            insert(BalanceAlertState)
            .values(user_id=user_id, alerted_at=alerted_at, balance_at_alert=balance)
            .on_conflict_do_update(
                index_elements=[BalanceAlertState.user_id],
                set_={
                    "alerted_at": alerted_at,
                    "balance_at_alert": balance,
                    "updated_at": func.now(),
                },
            )
        )
        self._session.execute(statement)

    def clear_alerted(self, user_id: UUID) -> None:
        """清除提醒标记，供发送失败后在下次使用时重试。"""

        self._session.execute(
            update(BalanceAlertState)
            .where(BalanceAlertState.user_id == user_id)
            .values(alerted_at=None, balance_at_alert=None, updated_at=func.now())
        )
