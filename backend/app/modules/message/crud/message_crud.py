"""消息、消息定向关系与已读记录的数据库访问。"""

from uuid import UUID

from sqlalchemy import ColumnElement, and_, exists, func, or_, select, update
from sqlmodel import Session

from app.modules.message.model import Message, MessageRead, MessageTarget, MessageType


class MessageCrud:
    """封装消息相关表的查询、定向关系维护与已读事实持久化。"""

    def __init__(self, session: Session) -> None:
        """绑定调用方提供的事务会话。"""

        self._session = session

    # 管理端

    def list_page(
        self,
        *,
        keyword: str | None,
        message_type: MessageType | None,
        is_active: bool | None,
        page: int,
        page_size: int,
    ) -> tuple[int, list[Message]]:
        """按筛选条件分页读取消息，按生效时间倒序。"""

        conditions: list[ColumnElement[bool]] = []
        if keyword:
            conditions.append(Message.title.ilike(f"%{keyword}%"))
        if message_type is not None:
            conditions.append(Message.type == message_type)
        if is_active is not None:
            conditions.append(Message.is_active.is_(is_active))
        total = self._session.scalar(select(func.count()).select_from(Message).where(*conditions)) or 0
        items = list(
            self._session.scalars(
                select(Message)
                .where(*conditions)
                .order_by(Message.start_at.desc(), Message.created_at.desc(), Message.id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        return total, items

    def get(self, message_id: UUID, *, include_deleted: bool = False) -> Message | None:
        """读取指定消息，可选包含已逻辑删除记录。"""

        return self._session.scalar(
            select(Message).where(Message.id == message_id).execution_options(include_deleted=include_deleted)
        )

    def add(self, message: Message) -> Message:
        """新增消息并刷新主键。"""

        self._session.add(message)
        self._session.flush()
        return message

    def list_targets(self, message_id: UUID) -> list[MessageTarget]:
        """读取消息当前全部未删除的定向关系。"""

        return list(
            self._session.scalars(
                select(MessageTarget)
                .where(MessageTarget.message_id == message_id)
                .order_by(MessageTarget.created_at, MessageTarget.id)
            )
        )

    def list_targets_by_message_ids(self, message_ids: list[UUID]) -> list[MessageTarget]:
        """批量读取多条消息的未删除定向关系，避免列表查询逐条访问。"""

        if not message_ids:
            return []
        return list(self._session.scalars(select(MessageTarget).where(MessageTarget.message_id.in_(message_ids))))

    def replace_targets(
        self,
        message_id: UUID,
        *,
        user_ids: list[UUID],
        group_ids: list[int],
    ) -> None:
        """整体替换消息定向关系，保留撤销记录的逻辑删除历史。"""

        existing = list(
            self._session.scalars(
                select(MessageTarget)
                .where(MessageTarget.message_id == message_id)
                .execution_options(include_deleted=True)
            )
        )
        self._session.execute(
            update(MessageTarget)
            .where(MessageTarget.message_id == message_id, MessageTarget.is_del.is_(False))
            .values(is_del=True)
        )
        by_user = {item.user_id: item for item in existing if item.user_id is not None}
        by_group = {item.token_group_id: item for item in existing if item.token_group_id is not None}
        for user_id in dict.fromkeys(user_ids):
            self._revive_or_add(existing=by_user.get(user_id), message_id=message_id, user_id=user_id)
        for group_id in dict.fromkeys(group_ids):
            self._revive_or_add(existing=by_group.get(group_id), message_id=message_id, token_group_id=group_id)
        self._session.flush()

    def soft_delete(self, message: Message) -> None:
        """逻辑删除消息，并同步删除其定向关系，保留历史行。"""

        message.is_del = True
        self._session.add(message)
        self._session.execute(
            update(MessageTarget)
            .where(MessageTarget.message_id == message.id, MessageTarget.is_del.is_(False))
            .values(is_del=True)
        )

    # 用户端

    def list_visible_page(
        self,
        *,
        user_id: UUID,
        group_ids: list[int],
        message_type: MessageType | None,
        unread_only: bool,
        page: int,
        page_size: int,
    ) -> tuple[int, list[tuple[Message, bool]]]:
        """分页读取对用户可见的消息并附带已读标记，按生效时间倒序。"""

        visible = self._visible_condition(user_id=user_id, group_ids=group_ids)
        is_read = self._read_exists(user_id)
        conditions: list[ColumnElement[bool]] = [visible]
        if message_type is not None:
            conditions.append(Message.type == message_type)
        if unread_only:
            conditions.append(~is_read)
        total = self._session.scalar(select(func.count()).select_from(Message).where(*conditions)) or 0
        rows = self._session.execute(
            select(Message, is_read.label("is_read"))
            .where(*conditions)
            .order_by(Message.start_at.desc(), Message.created_at.desc(), Message.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return total, [(row[0], bool(row[1])) for row in rows]

    def count_visible_unread(self, *, user_id: UUID, group_ids: list[int]) -> int:
        """统计当前对用户可见且未读的消息数量。"""

        visible = self._visible_condition(user_id=user_id, group_ids=group_ids)
        return (
            self._session.scalar(select(func.count()).select_from(Message).where(visible, ~self._read_exists(user_id)))
            or 0
        )

    def get_visible(self, *, message_id: UUID, user_id: UUID, group_ids: list[int]) -> Message | None:
        """读取对指定用户可见的消息，不可见时返回空。"""

        visible = self._visible_condition(user_id=user_id, group_ids=group_ids)
        return self._session.scalar(select(Message).where(Message.id == message_id, visible))

    def list_visible_unread_ids(self, *, user_id: UUID, group_ids: list[int]) -> list[UUID]:
        """列出当前对用户可见且未读的消息标识。"""

        visible = self._visible_condition(user_id=user_id, group_ids=group_ids)
        return list(self._session.scalars(select(Message.id).where(visible, ~self._read_exists(user_id))))

    def is_read(self, *, user_id: UUID, message_id: UUID) -> bool:
        """判断用户是否已读指定消息。"""

        return (
            self._session.scalar(
                select(MessageRead.id).where(
                    MessageRead.message_id == message_id,
                    MessageRead.user_id == user_id,
                )
            )
            is not None
        )

    def mark_read(self, *, user_id: UUID, message_id: UUID, read_at) -> None:
        """标记单条消息已读，复用或新建已读记录以保证幂等。"""

        existing = self._session.scalar(
            select(MessageRead)
            .where(MessageRead.message_id == message_id, MessageRead.user_id == user_id)
            .execution_options(include_deleted=True)
        )
        if existing is None:
            self._session.add(MessageRead(message_id=message_id, user_id=user_id, read_at=read_at))
        elif existing.is_del:
            existing.is_del = False
            existing.read_at = read_at
            self._session.add(existing)
        self._session.flush()

    def add_reads(self, *, user_id: UUID, message_ids: list[UUID], read_at) -> None:
        """批量标记消息已读，仅补齐尚未标记的消息。"""

        if not message_ids:
            return
        existing = list(
            self._session.scalars(
                select(MessageRead)
                .where(MessageRead.user_id == user_id, MessageRead.message_id.in_(message_ids))
                .execution_options(include_deleted=True)
            )
        )
        by_message = {item.message_id: item for item in existing}
        for message_id in dict.fromkeys(message_ids):
            record = by_message.get(message_id)
            if record is None:
                self._session.add(MessageRead(message_id=message_id, user_id=user_id, read_at=read_at))
            elif record.is_del:
                record.is_del = False
                record.read_at = read_at
                self._session.add(record)
        self._session.flush()

    # 内部

    def _revive_or_add(
        self,
        *,
        existing: MessageTarget | None,
        message_id: UUID,
        user_id: UUID | None = None,
        token_group_id: int | None = None,
    ) -> None:
        """复用历史定向行或新建，避免重复插入同一目标。"""

        if existing is not None:
            existing.is_del = False
            self._session.add(existing)
            return
        self._session.add(
            MessageTarget(
                message_id=message_id,
                user_id=user_id,
                token_group_id=token_group_id,
            )
        )

    @staticmethod
    def _read_exists(user_id: UUID) -> ColumnElement[bool]:
        """构造“当前用户已读该消息”的存在性子查询条件。"""

        return exists(
            select(MessageRead.id).where(
                MessageRead.message_id == Message.id,
                MessageRead.user_id == user_id,
            )
        )

    @staticmethod
    def _visible_condition(*, user_id: UUID, group_ids: list[int]) -> ColumnElement[bool]:
        """构造消息对指定用户可见的查询条件。"""

        now = func.now()
        target_terms: list[ColumnElement[bool]] = [MessageTarget.user_id == user_id]
        if group_ids:
            target_terms.append(MessageTarget.token_group_id.in_(group_ids))
        target_match = exists(
            select(MessageTarget.id).where(
                MessageTarget.message_id == Message.id,
                MessageTarget.is_del.is_(False),
                or_(*target_terms),
            )
        )
        return and_(
            Message.is_active.is_(True),
            Message.start_at <= now,
            or_(Message.expires_at.is_(None), Message.expires_at > now),
            or_(Message.is_public.is_(True), target_match),
        )
