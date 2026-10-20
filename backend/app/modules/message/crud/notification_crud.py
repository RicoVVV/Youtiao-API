"""通知、通知定向关系与用户关闭记录的数据库访问。"""

from uuid import UUID

from sqlalchemy import ColumnElement, and_, exists, func, or_, select, update
from sqlmodel import Session

from app.modules.message.model import Notification, NotificationDismissal, NotificationTarget


class NotificationCrud:
    """封装通知相关表的查询、定向关系维护、生效互斥与关闭事实持久化。"""

    def __init__(self, session: Session) -> None:
        """绑定调用方提供的事务会话。"""

        self._session = session

    # 管理端

    def list_page(
        self, *, keyword: str | None, is_active: bool | None, page: int, page_size: int
    ) -> tuple[int, list[Notification]]:
        """按筛选条件分页读取通知，按创建时间倒序。"""

        conditions: list[ColumnElement[bool]] = []
        if keyword:
            conditions.append(Notification.title.ilike(f"%{keyword}%"))
        if is_active is not None:
            conditions.append(Notification.is_active.is_(is_active))
        total = self._session.scalar(select(func.count()).select_from(Notification).where(*conditions)) or 0
        items = list(
            self._session.scalars(
                select(Notification)
                .where(*conditions)
                .order_by(Notification.created_at.desc(), Notification.id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        return total, items

    def get(self, notification_id: UUID, *, include_deleted: bool = False) -> Notification | None:
        """读取指定通知，可选包含已逻辑删除记录。"""

        return self._session.scalar(
            select(Notification)
            .where(Notification.id == notification_id)
            .execution_options(include_deleted=include_deleted)
        )

    def add(self, notification: Notification) -> Notification:
        """新增通知并刷新主键。"""

        self._session.add(notification)
        self._session.flush()
        return notification

    def list_targets(self, notification_id: UUID) -> list[NotificationTarget]:
        """读取通知当前全部未删除的定向关系。"""

        return list(
            self._session.scalars(
                select(NotificationTarget)
                .where(NotificationTarget.notification_id == notification_id)
                .order_by(NotificationTarget.created_at, NotificationTarget.id)
            )
        )

    def list_targets_by_notification_ids(self, notification_ids: list[UUID]) -> list[NotificationTarget]:
        """批量读取多条通知的未删除定向关系，避免列表查询逐条访问。"""

        if not notification_ids:
            return []
        return list(
            self._session.scalars(
                select(NotificationTarget).where(NotificationTarget.notification_id.in_(notification_ids))
            )
        )

    def replace_targets(
        self,
        notification_id: UUID,
        *,
        user_ids: list[UUID],
        group_ids: list[int],
    ) -> None:
        """整体替换通知定向关系，保留撤销记录的逻辑删除历史。"""

        existing = list(
            self._session.scalars(
                select(NotificationTarget)
                .where(NotificationTarget.notification_id == notification_id)
                .execution_options(include_deleted=True)
            )
        )
        self._session.execute(
            update(NotificationTarget)
            .where(NotificationTarget.notification_id == notification_id, NotificationTarget.is_del.is_(False))
            .values(is_del=True)
        )
        by_user = {item.user_id: item for item in existing if item.user_id is not None}
        by_group = {item.token_group_id: item for item in existing if item.token_group_id is not None}
        for user_id in dict.fromkeys(user_ids):
            self._revive_or_add(existing=by_user.get(user_id), notification_id=notification_id, user_id=user_id)
        for group_id in dict.fromkeys(group_ids):
            self._revive_or_add(
                existing=by_group.get(group_id), notification_id=notification_id, token_group_id=group_id
            )
        self._session.flush()

    def soft_delete(self, notification: Notification) -> None:
        """逻辑删除通知，并同步删除其定向关系，保留历史行。"""

        notification.is_del = True
        self._session.add(notification)
        self._session.execute(
            update(NotificationTarget)
            .where(NotificationTarget.notification_id == notification.id, NotificationTarget.is_del.is_(False))
            .values(is_del=True)
        )

    def deactivate_all_except(self, notification_id: UUID) -> None:
        """把除指定通知外的其它生效中通知置为下架，保证全局唯一生效中。"""

        self._session.execute(
            update(Notification)
            .where(
                Notification.id != notification_id,
                Notification.is_active.is_(True),
                Notification.is_del.is_(False),
            )
            .values(is_active=False)
        )

    # 用户端

    def current(self, *, user_id: UUID, group_ids: list[int]) -> Notification | None:
        """读取当前唯一生效中且未被该用户关闭的通知。"""

        visible = self._visible_condition(user_id=user_id, group_ids=group_ids)
        return self._session.scalar(
            select(Notification)
            .where(visible, ~self._dismissed_exists(user_id))
            .order_by(Notification.start_at.desc(), Notification.created_at.desc(), Notification.id)
            .limit(1)
        )

    def count_pending(self, *, user_id: UUID, group_ids: list[int]) -> int:
        """统计当前用户可见且未关闭的生效中通知数量（全局唯一，最多为 1）。"""

        visible = self._visible_condition(user_id=user_id, group_ids=group_ids)
        return (
            self._session.scalar(
                select(func.count()).select_from(Notification).where(visible, ~self._dismissed_exists(user_id))
            )
            or 0
        )

    def list_history_page(
        self, *, user_id: UUID, group_ids: list[int], page: int, page_size: int
    ) -> tuple[int, list[tuple[Notification, bool]]]:
        """分页读取用户曾经可见的通知历史并附带关闭标记，按生效时间倒序。"""

        visible = self._history_condition(user_id=user_id, group_ids=group_ids)
        dismissed = self._dismissed_exists(user_id)
        total = self._session.scalar(select(func.count()).select_from(Notification).where(visible)) or 0
        rows = self._session.execute(
            select(Notification, dismissed.label("is_dismissed"))
            .where(visible)
            .order_by(Notification.start_at.desc(), Notification.created_at.desc(), Notification.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return total, [(row[0], bool(row[1])) for row in rows]

    def get_history(self, *, notification_id: UUID, user_id: UUID, group_ids: list[int]):
        """读取用户历史上可见的指定通知，不可见时返回空。"""

        visible = self._history_condition(user_id=user_id, group_ids=group_ids)
        return self._session.scalar(select(Notification).where(Notification.id == notification_id, visible))

    def is_dismissed(self, *, user_id: UUID, notification_id: UUID) -> bool:
        """判断用户是否已关闭指定通知。"""

        return (
            self._session.scalar(
                select(NotificationDismissal.id).where(
                    NotificationDismissal.notification_id == notification_id,
                    NotificationDismissal.user_id == user_id,
                )
            )
            is not None
        )

    def dismiss(self, *, user_id: UUID, notification_id: UUID, dismissed_at) -> None:
        """记录用户关闭通知，复用或新建记录以保证幂等。"""

        existing = self._session.scalar(
            select(NotificationDismissal)
            .where(
                NotificationDismissal.notification_id == notification_id,
                NotificationDismissal.user_id == user_id,
            )
            .execution_options(include_deleted=True)
        )
        if existing is None:
            self._session.add(
                NotificationDismissal(notification_id=notification_id, user_id=user_id, dismissed_at=dismissed_at)
            )
        elif existing.is_del:
            existing.is_del = False
            existing.dismissed_at = dismissed_at
            self._session.add(existing)
        self._session.flush()

    # 内部

    def _revive_or_add(
        self,
        *,
        existing: NotificationTarget | None,
        notification_id: UUID,
        user_id: UUID | None = None,
        token_group_id: int | None = None,
    ) -> None:
        """复用历史定向行或新建，避免重复插入同一目标。"""

        if existing is not None:
            existing.is_del = False
            self._session.add(existing)
            return
        self._session.add(
            NotificationTarget(
                notification_id=notification_id,
                user_id=user_id,
                token_group_id=token_group_id,
            )
        )

    @classmethod
    def _target_terms(cls, user_id: UUID, group_ids: list[int]) -> list[ColumnElement[bool]]:
        terms: list[ColumnElement[bool]] = [NotificationTarget.user_id == user_id]
        if group_ids:
            terms.append(NotificationTarget.token_group_id.in_(group_ids))
        return terms

    @classmethod
    def _target_match(cls, user_id: UUID, group_ids: list[int]) -> ColumnElement[bool]:
        """构造“命中任一通知定向目标”的存在性子查询条件。"""

        return exists(
            select(NotificationTarget.id).where(
                NotificationTarget.notification_id == Notification.id,
                NotificationTarget.is_del.is_(False),
                or_(*cls._target_terms(user_id, group_ids)),
            )
        )

    @classmethod
    def _history_condition(cls, *, user_id: UUID, group_ids: list[int]) -> ColumnElement[bool]:
        """构造“用户曾经可见”的条件：已到生效时间且命中定向或全体可见。"""

        return and_(
            Notification.start_at <= func.now(),
            or_(Notification.is_public.is_(True), cls._target_match(user_id, group_ids)),
        )

    @classmethod
    def _visible_condition(cls, *, user_id: UUID, group_ids: list[int]) -> ColumnElement[bool]:
        """构造通知对指定用户当前可见的查询条件。"""

        now = func.now()
        return and_(
            Notification.is_active.is_(True),
            Notification.start_at <= now,
            or_(Notification.expires_at.is_(None), Notification.expires_at > now),
            or_(Notification.is_public.is_(True), cls._target_match(user_id, group_ids)),
        )

    @staticmethod
    def _dismissed_exists(user_id: UUID) -> ColumnElement[bool]:
        """构造“当前用户已关闭该通知”的存在性子查询条件。"""

        return exists(
            select(NotificationDismissal.id).where(
                NotificationDismissal.notification_id == Notification.id,
                NotificationDismissal.user_id == user_id,
            )
        )
