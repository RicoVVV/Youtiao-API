"""管理员用户查询数据访问，集中跨模块运营统计的 ORM 查询。"""

from sqlalchemy import func, select
from sqlmodel import Session

from app.modules.channels.model.concurrency import UserConcurrencyLease
from app.modules.usage.model import UsageRecord, UsageRecordStatus
from app.modules.user.model.user import User
from app.modules.wallet.model import Wallet


class AdminUserCrud:
    """封装管理员用户列表及其跨业务运营统计查询。"""

    def __init__(self, session: Session) -> None:
        """绑定调用方管理的数据库会话。"""

        self._session = session

    def list_user_statistics(self, *, page: int, page_size: int) -> tuple[int, list[tuple[object, ...]]]:
        """查询分页用户及余额、用量和活跃租约统计。"""

        total = int(self._session.scalar(select(func.count()).select_from(User)) or 0)
        balance_by_user = select(Wallet.user_id.label("user_id"), Wallet.balance.label("balance")).subquery()
        usage_by_user = (
            select(UsageRecord.user_id.label("user_id"), func.coalesce(func.sum(UsageRecord.amount), 0).label("usage"))
            .where(UsageRecord.status == UsageRecordStatus.succeeded)
            .group_by(UsageRecord.user_id)
            .subquery()
        )
        active_leases_by_user = (
            select(UserConcurrencyLease.user_id.label("user_id"), func.count().label("active_lease_count"))
            .where(UserConcurrencyLease.released_at.is_(None))
            .group_by(UserConcurrencyLease.user_id)
            .subquery()
        )
        rows = self._session.execute(
            select(
                User,
                func.coalesce(balance_by_user.c.balance, 0),
                func.coalesce(usage_by_user.c.usage, 0),
                func.coalesce(active_leases_by_user.c.active_lease_count, 0),
            )
            .outerjoin(balance_by_user, balance_by_user.c.user_id == User.id)
            .outerjoin(usage_by_user, usage_by_user.c.user_id == User.id)
            .outerjoin(active_leases_by_user, active_leases_by_user.c.user_id == User.id)
            .order_by(User.created_at.desc(), User.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return total, rows

    def get_user_statistics_by_username(self, *, username: str) -> tuple[object, ...] | None:
        """按用户名精确查询单个用户及其余额、用量和活跃租约统计。"""

        balance_by_user = select(Wallet.user_id.label("user_id"), Wallet.balance.label("balance")).subquery()
        usage_by_user = (
            select(UsageRecord.user_id.label("user_id"), func.coalesce(func.sum(UsageRecord.amount), 0).label("usage"))
            .where(UsageRecord.status == UsageRecordStatus.succeeded)
            .group_by(UsageRecord.user_id)
            .subquery()
        )
        active_leases_by_user = (
            select(UserConcurrencyLease.user_id.label("user_id"), func.count().label("active_lease_count"))
            .where(UserConcurrencyLease.released_at.is_(None))
            .group_by(UserConcurrencyLease.user_id)
            .subquery()
        )
        row = self._session.execute(
            select(
                User,
                func.coalesce(balance_by_user.c.balance, 0),
                func.coalesce(usage_by_user.c.usage, 0),
                func.coalesce(active_leases_by_user.c.active_lease_count, 0),
            )
            .outerjoin(balance_by_user, balance_by_user.c.user_id == User.id)
            .outerjoin(usage_by_user, usage_by_user.c.user_id == User.id)
            .outerjoin(active_leases_by_user, active_leases_by_user.c.user_id == User.id)
            .where(User.username == username)
        ).one_or_none()
        return row
