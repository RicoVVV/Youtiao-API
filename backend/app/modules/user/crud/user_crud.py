"""用户账号及账户运营统计的数据访问。"""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import func
from sqlmodel import Session, select

from app.modules.usage.model import UsageRecord, UsageRecordStatus
from app.modules.user.model.user import User
from app.modules.wallet.model import Wallet


class UserCrud:
    """封装用户账号的查询和创建操作。"""

    def __init__(self, session: Session) -> None:
        """绑定外部传入的数据库会话。"""

        self._session = session

    def get_by_id(self, user_id: UUID) -> User | None:
        """按用户标识查询用户。"""

        return self._session.get(User, user_id)

    def list_by_ids(self, user_ids: list[UUID]) -> list[User]:
        """按传入标识顺序读取用户，用于组装关联资源展示信息。"""

        users_by_id = {user.id: user for user in self._session.scalars(select(User).where(User.id.in_(user_ids)))}
        return [users_by_id[user_id] for user_id in user_ids if user_id in users_by_id]

    def get_profile_statistics(self, user_id: UUID) -> tuple[User, Decimal, Decimal] | None:
        """查询单个用户及余额、已结算用量。"""

        usage_by_user = (
            select(UsageRecord.user_id.label("user_id"), func.coalesce(func.sum(UsageRecord.amount), 0).label("usage"))
            .where(UsageRecord.status == UsageRecordStatus.succeeded)
            .group_by(UsageRecord.user_id)
            .subquery()
        )
        row = self._session.execute(
            select(
                User,
                func.coalesce(Wallet.balance, 0),
                func.coalesce(usage_by_user.c.usage, 0),
            )
            .outerjoin(Wallet, Wallet.user_id == User.id)
            .outerjoin(usage_by_user, usage_by_user.c.user_id == User.id)
            .where(User.id == user_id)
        ).one_or_none()
        if row is None:
            return None
        user, balance, usage = row
        return user, Decimal(balance), Decimal(usage)

    def get_by_username(self, username: str) -> User | None:
        """按唯一登录名查询用户。"""

        return self._session.scalar(select(User).where(User.username == username))

    def get_by_email(self, email: str) -> User | None:
        """按邮箱（不区分大小写）查询未删除的用户。"""

        return self._session.scalar(select(User).where(func.lower(User.email) == email.lower()).limit(1))

    def create(self, *, username: str, password_hash: str, is_admin: bool = False, email: str | None = None) -> User:
        """创建用户并刷新主键，以支持同一事务创建关联记录。"""

        user = User(username=username, password_hash=password_hash, is_admin=is_admin, email=email)
        self._session.add(user)
        self._session.flush()
        return user

    def has_admin(self) -> bool:
        """判断系统是否已存在未逻辑删除的管理员账号。"""

        return bool(self._session.scalar(select(func.count()).select_from(User).where(User.is_admin.is_(True))))

    def acquire_initial_admin_lock(self) -> None:
        self._session.execute(select(func.pg_advisory_xact_lock(817263541)))
