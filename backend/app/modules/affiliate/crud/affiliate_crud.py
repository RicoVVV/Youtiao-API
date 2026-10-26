"""邀请返利数据访问层，集中处理邀请关系、额度变动与流水查询。

本模块不提交或回滚调用方事务，也不处理 HTTP 错误映射。
"""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import aliased
from sqlmodel import Session

from app.core.affiliate import generate_affiliate_code
from app.modules.affiliate.model import AffiliateLedger, AffiliateLedgerAction, UserAffiliate
from app.modules.user.model.user import User
from app.modules.wallet.model import RechargeOrder


class AffiliateCrud:
    """封装邀请返利持久化访问，不管理事务提交或回滚。"""

    def __init__(self, session: Session) -> None:
        """绑定调用方管理的数据库会话。"""

        self._session = session

    def get_by_user_id(self, user_id: UUID) -> UserAffiliate | None:
        """按用户读取邀请档案。"""

        return self._session.scalar(select(UserAffiliate).where(UserAffiliate.user_id == user_id))

    def get_by_user_id_for_update(self, user_id: UUID) -> UserAffiliate | None:
        """锁定用户邀请档案，串行化额度转出。"""

        return self._session.scalar(select(UserAffiliate).where(UserAffiliate.user_id == user_id).with_for_update())

    def get_by_code(self, code: str) -> UserAffiliate | None:
        """按邀请码读取邀请档案。"""

        return self._session.scalar(select(UserAffiliate).where(UserAffiliate.aff_code == code))

    def is_user_deleted(self, user_id: UUID) -> bool:
        """判断用户是否已逻辑删除；用户行缺失时按不可用处理。"""

        is_deleted = self._session.scalar(
            select(User.is_del).where(User.id == user_id).execution_options(include_deleted=True)
        )
        return is_deleted is None or bool(is_deleted)

    def increment_invite_count(self, inviter_id: UUID) -> None:
        """原子增加邀请人的绑定人数。"""

        self._session.execute(
            update(UserAffiliate)
            .where(UserAffiliate.user_id == inviter_id)
            .values(aff_count=UserAffiliate.aff_count + 1)
        )

    def decrement_invite_count(self, inviter_id: UUID) -> None:
        """原子减少邀请人的绑定人数，且不低于零。"""

        self._session.execute(
            update(UserAffiliate)
            .where(UserAffiliate.user_id == inviter_id)
            .values(aff_count=func.greatest(UserAffiliate.aff_count - 1, 0))
        )

    def ensure_user_affiliate(self, user_id: UUID) -> UserAffiliate:
        """读取或创建用户邀请档案，邀请码冲突时自动重试。"""

        existing = self.get_by_user_id(user_id)
        if existing is not None:
            return existing
        for _ in range(12):
            try:
                with self._session.begin_nested():
                    self._session.add(UserAffiliate(user_id=user_id, aff_code=generate_affiliate_code()))
                    self._session.flush()
            except IntegrityError as exc:
                if not _is_unique_violation(exc):
                    raise
                existing = self.get_by_user_id(user_id)
                if existing is not None:
                    return existing
                continue
            created = self.get_by_user_id(user_id)
            if created is not None:
                return created
        raise RuntimeError("无法生成唯一邀请码")

    def bind_inviter(self, user_id: UUID, inviter_id: UUID) -> bool:
        """仅在尚未绑定时写入上级，并原子增加邀请人的绑定人数。"""

        statement = (
            update(UserAffiliate)
            .where(UserAffiliate.user_id == user_id, UserAffiliate.inviter_id.is_(None))
            .values(inviter_id=inviter_id)
            .returning(UserAffiliate.user_id)
        )
        if self._session.execute(statement).scalar_one_or_none() is None:
            return False
        self.increment_invite_count(inviter_id)
        return True

    def get_accrued_total(self, inviter_id: UUID, invitee_id: UUID) -> Decimal:
        """汇总某被邀请人已为邀请人产生的返利总额。"""

        amount = self._session.scalar(
            select(func.coalesce(func.sum(AffiliateLedger.amount), 0)).where(
                AffiliateLedger.user_id == inviter_id,
                AffiliateLedger.source_user_id == invitee_id,
                AffiliateLedger.action == AffiliateLedgerAction.accrue,
            )
        )
        return _to_decimal(amount)

    def create_accrual(self, ledger: AffiliateLedger) -> bool:
        """写入返利流水；同一订单已发过返利时返回 False。"""

        values: dict = {
            "id": ledger.id,
            "user_id": ledger.user_id,
            "action": ledger.action,
            "amount": ledger.amount,
            "source_user_id": ledger.source_user_id,
            "source_order_id": ledger.source_order_id,
            "frozen_until": ledger.frozen_until,
        }
        if ledger.created_at is not None:
            values["created_at"] = ledger.created_at
        if ledger.updated_at is not None:
            values["updated_at"] = ledger.updated_at
        statement = (
            pg_insert(AffiliateLedger)
            .values(**values)
            .on_conflict_do_nothing(
                index_elements=[AffiliateLedger.source_order_id],
                index_where=text("action = 'accrue' AND source_order_id IS NOT NULL"),
            )
            .returning(AffiliateLedger.id)
        )
        return self._session.execute(statement).scalar_one_or_none() is not None

    def add_accrued_quota(self, user_id: UUID, amount: Decimal, *, frozen: bool) -> None:
        """按冻结状态把返利计入可用池或冻结池，并累计历史总额。"""

        values: dict = {"history_quota": UserAffiliate.history_quota + amount}
        if frozen:
            values["frozen_quota"] = UserAffiliate.frozen_quota + amount
        else:
            values["available_quota"] = UserAffiliate.available_quota + amount
        self._session.execute(update(UserAffiliate).where(UserAffiliate.user_id == user_id).values(**values))

    def thaw_frozen(self, user_id: UUID) -> Decimal:
        """把已到期的冻结流水解冻并移入可用池，返回本次解冻金额。

        先锁定用户档案行，保证与转出流程使用相同的加锁顺序，避免并发死锁。
        """

        if self.get_by_user_id_for_update(user_id) is None:
            return Decimal("0")
        statement = (
            update(AffiliateLedger)
            .where(
                AffiliateLedger.user_id == user_id,
                AffiliateLedger.action == AffiliateLedgerAction.accrue,
                AffiliateLedger.frozen_until.is_not(None),
                AffiliateLedger.frozen_until <= datetime.now(UTC),
            )
            .values(frozen_until=None)
            .returning(AffiliateLedger.amount)
        )
        thawed = sum((_to_decimal(item) for item in self._session.execute(statement).scalars().all()), Decimal("0"))
        if thawed > 0:
            self._session.execute(
                update(UserAffiliate)
                .where(UserAffiliate.user_id == user_id)
                .values(
                    available_quota=UserAffiliate.available_quota + thawed,
                    frozen_quota=func.greatest(UserAffiliate.frozen_quota - thawed, Decimal("0")),
                )
            )
        return thawed

    def add_transfer_ledger(self, ledger: AffiliateLedger) -> AffiliateLedger:
        """登记一条返利转入余额流水。"""

        self._session.add(ledger)
        return ledger

    def count_invitees(self, inviter_id: UUID) -> int:
        """统计邀请人当前未被注销的被邀请人总数。"""

        return int(
            self._session.scalar(
                select(func.count(UserAffiliate.user_id))
                .join(User, User.id == UserAffiliate.user_id)
                .where(UserAffiliate.inviter_id == inviter_id, User.is_del.is_(False))
            )
            or 0
        )

    def list_invitees(self, inviter_id: UUID, *, page: int, page_size: int) -> list:
        """分页读取被邀请人及其累计返利。"""

        rebate_subquery = (
            select(
                AffiliateLedger.source_user_id.label("invitee_id"),
                func.coalesce(func.sum(AffiliateLedger.amount), 0).label("total_rebate"),
            )
            .where(
                AffiliateLedger.user_id == inviter_id,
                AffiliateLedger.action == AffiliateLedgerAction.accrue,
            )
            .group_by(AffiliateLedger.source_user_id)
            .subquery()
        )
        statement = (
            select(UserAffiliate, User, func.coalesce(rebate_subquery.c.total_rebate, 0))
            .join(User, User.id == UserAffiliate.user_id)
            .outerjoin(rebate_subquery, rebate_subquery.c.invitee_id == UserAffiliate.user_id)
            .where(UserAffiliate.inviter_id == inviter_id, User.is_del.is_(False))
            .order_by(UserAffiliate.created_at.desc(), UserAffiliate.user_id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(self._session.execute(statement).all())

    def count_ledger(self, user_id: UUID) -> int:
        """统计用户自己的返利流水数量。"""

        return int(
            self._session.scalar(select(func.count(AffiliateLedger.id)).where(AffiliateLedger.user_id == user_id)) or 0
        )

    def list_ledger(self, user_id: UUID, *, page: int, page_size: int) -> list:
        """分页读取用户自己的返利流水。"""

        statement = (
            select(AffiliateLedger, User.username, RechargeOrder.order_no)
            .outerjoin(User, User.id == AffiliateLedger.source_user_id)
            .outerjoin(RechargeOrder, RechargeOrder.id == AffiliateLedger.source_order_id)
            .where(AffiliateLedger.user_id == user_id)
            .order_by(AffiliateLedger.created_at.desc(), AffiliateLedger.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(self._session.execute(statement).all())

    def count_accrue_records(self) -> int:
        """统计全部返利产生流水，保留已注销用户的历史记录。"""

        return int(
            self._session.scalar(
                select(func.count(AffiliateLedger.id)).where(AffiliateLedger.action == AffiliateLedgerAction.accrue)
            )
            or 0
        )

    def list_accrue_records(self, *, page: int, page_size: int) -> list:
        """分页读取全部返利产生流水及订单信息。"""

        inviter = aliased(User)
        invitee = aliased(User)
        statement = (
            select(
                AffiliateLedger,
                inviter.username,
                invitee.username,
                RechargeOrder.order_no,
                RechargeOrder.amount,
            )
            .join(inviter, inviter.id == AffiliateLedger.user_id)
            .outerjoin(invitee, invitee.id == AffiliateLedger.source_user_id)
            .outerjoin(RechargeOrder, RechargeOrder.id == AffiliateLedger.source_order_id)
            .where(AffiliateLedger.action == AffiliateLedgerAction.accrue)
            .order_by(AffiliateLedger.created_at.desc(), AffiliateLedger.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .execution_options(include_deleted=True)
        )
        return list(self._session.execute(statement).all())

    def count_transfer_records(self) -> int:
        """统计全部返利转出流水，保留已注销用户的历史记录。"""

        return int(
            self._session.scalar(
                select(func.count(AffiliateLedger.id)).where(AffiliateLedger.action == AffiliateLedgerAction.transfer)
            )
            or 0
        )

    def list_transfer_records(self, *, page: int, page_size: int) -> list:
        """分页读取全部返利转出流水。"""

        statement = (
            select(AffiliateLedger, User.username)
            .join(User, User.id == AffiliateLedger.user_id)
            .where(AffiliateLedger.action == AffiliateLedgerAction.transfer)
            .order_by(AffiliateLedger.created_at.desc(), AffiliateLedger.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .execution_options(include_deleted=True)
        )
        return list(self._session.execute(statement).all())

    def count_users(self, search: str | None = None) -> int:
        """统计拥有邀请档案的用户数量。"""

        statement = select(func.count(UserAffiliate.user_id)).join(User, User.id == UserAffiliate.user_id)
        statement = statement.where(User.is_del.is_(False))
        statement = _apply_user_search(statement, search)
        return int(self._session.scalar(statement) or 0)

    def list_users(self, *, page: int, page_size: int, search: str | None = None) -> list:
        """分页读取拥有邀请档案的用户及其上级。"""

        inviter = aliased(User)
        statement = (
            select(UserAffiliate, User, inviter.username)
            .join(User, User.id == UserAffiliate.user_id)
            .outerjoin(inviter, inviter.id == UserAffiliate.inviter_id)
            .where(User.is_del.is_(False))
        )
        statement = _apply_user_search(statement, search)
        statement = (
            statement.order_by(UserAffiliate.updated_at.desc(), UserAffiliate.user_id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(self._session.execute(statement).all())

    def get_user_overview(self, user_id: UUID) -> tuple | None:
        """读取单个用户的邀请档案、账号与上级用户名。"""

        inviter = aliased(User)
        row = self._session.execute(
            select(UserAffiliate, User, inviter.username)
            .join(User, User.id == UserAffiliate.user_id)
            .outerjoin(inviter, inviter.id == UserAffiliate.inviter_id)
            .where(UserAffiliate.user_id == user_id, User.is_del.is_(False))
        ).one_or_none()
        if row is None:
            return None
        rebated_count = int(
            self._session.scalar(
                select(func.count(func.distinct(AffiliateLedger.source_user_id)))
                .join(User, User.id == AffiliateLedger.source_user_id)
                .where(
                    AffiliateLedger.user_id == user_id,
                    AffiliateLedger.action == AffiliateLedgerAction.accrue,
                    User.is_del.is_(False),
                )
            )
            or 0
        )
        return row[0], row[1], row[2], rebated_count

    def flush(self) -> None:
        """刷新待写入实体，不提交事务。"""

        self._session.flush()


def _apply_user_search(statement, search: str | None):
    """按用户名或邮箱追加模糊搜索条件。"""

    keyword = (search or "").strip()
    if not keyword:
        return statement
    pattern = f"%{keyword}%"
    return statement.where(or_(User.username.ilike(pattern), User.email.ilike(pattern)))


def _to_decimal(value) -> Decimal:
    """把数据库返回值安全转换为 Decimal。"""

    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _is_unique_violation(exc: IntegrityError) -> bool:
    """判断异常是否由 PostgreSQL 唯一约束触发。"""

    return getattr(exc.orig, "pgcode", None) == "23505"
