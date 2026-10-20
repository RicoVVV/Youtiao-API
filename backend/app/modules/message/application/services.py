"""站内消息与通知的用户端应用服务，以及统一收件箱编排。"""

import enum
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlmodel import Session

from app.core.errors import NotFoundError
from app.modules.message.crud import MessageCrud, NotificationCrud
from app.modules.message.model import Message, MessageType, Notification
from app.modules.user.crud.token_group_crud import TokenGroupCrud


class InboxCategory(str, enum.Enum):
    """收件箱统一列表的类别，用于前端 tab 按字段取消息或通知。"""

    message = "message"
    notification = "notification"


def _resolve_audience(session: Session, user_id: UUID) -> list[int]:
    """解析用户可见性判定所需的全部可用分组。"""

    return [group.id for group in TokenGroupCrud(session).list_available_groups(user_id)]


class MessageService:
    """承载用户端读取可见消息与已读跟踪用例。"""

    def __init__(self, session: Session) -> None:
        """绑定请求级事务会话与消息数据访问。"""

        self._session = session
        self._crud = MessageCrud(session)

    def list_page(
        self,
        *,
        user_id: UUID,
        message_type: MessageType | None,
        unread_only: bool,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        """分页返回当前用户可见的消息，并按需附带已读标记。"""

        group_ids = _resolve_audience(self._session, user_id)
        total, rows = self._crud.list_visible_page(
            user_id=user_id,
            group_ids=group_ids,
            message_type=message_type,
            unread_only=unread_only,
            page=page,
            page_size=page_size,
        )
        return {
            "items": [self._user_projection(message, is_read) for message, is_read in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def get_detail(self, *, user_id: UUID, message_id: UUID) -> dict[str, Any]:
        """返回当前用户可见的单条消息详情，不可见时按不存在处理。"""

        group_ids = _resolve_audience(self._session, user_id)
        message = self._crud.get_visible(message_id=message_id, user_id=user_id, group_ids=group_ids)
        if message is None:
            raise NotFoundError("消息不存在")
        is_read = self._crud.is_read(user_id=user_id, message_id=message_id)
        return self._user_projection(message, is_read)

    def unread_count(self, *, user_id: UUID) -> int:
        """返回当前用户可见且未读的消息数量。"""

        group_ids = _resolve_audience(self._session, user_id)
        return self._crud.count_visible_unread(user_id=user_id, group_ids=group_ids)

    def mark_read(self, *, user_id: UUID, message_id: UUID) -> dict[str, Any]:
        """标记单条可见消息已读。"""

        group_ids = _resolve_audience(self._session, user_id)
        message = self._crud.get_visible(message_id=message_id, user_id=user_id, group_ids=group_ids)
        if message is None:
            raise NotFoundError("消息不存在")
        try:
            self._crud.mark_read(user_id=user_id, message_id=message_id, read_at=datetime.now(UTC))
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
        return {"success": True}

    def mark_all_read(self, *, user_id: UUID) -> dict[str, Any]:
        """将当前用户全部可见未读消息标记为已读。"""

        group_ids = _resolve_audience(self._session, user_id)
        unread_ids = self._crud.list_visible_unread_ids(user_id=user_id, group_ids=group_ids)
        try:
            self._crud.add_reads(user_id=user_id, message_ids=unread_ids, read_at=datetime.now(UTC))
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
        return {"marked_count": len(unread_ids)}

    @staticmethod
    def _user_projection(message: Message, is_read: bool) -> dict[str, Any]:
        return {
            "id": message.id,
            "title": message.title,
            "content": message.content,
            "type": message.type.value,
            "start_at": message.start_at,
            "expires_at": message.expires_at,
            "created_at": message.created_at,
            "is_read": is_read,
        }


class NotificationService:
    """承载用户端通知弹窗读取、历史回看与关闭用例。"""

    def __init__(self, session: Session) -> None:
        """绑定请求级事务会话与通知数据访问。"""

        self._session = session
        self._crud = NotificationCrud(session)

    def current(self, *, user_id: UUID) -> dict[str, Any]:
        """返回当前唯一生效中且未被该用户关闭的通知，无则返回空。"""

        group_ids = _resolve_audience(self._session, user_id)
        notification = self._crud.current(user_id=user_id, group_ids=group_ids)
        return {"notification": None if notification is None else self._user_projection(notification, False)}

    def list_history_page(self, *, user_id: UUID, page: int, page_size: int) -> dict[str, Any]:
        """分页返回当前用户历史上可见的通知，并附带关闭标记。"""

        group_ids = _resolve_audience(self._session, user_id)
        total, rows = self._crud.list_history_page(
            user_id=user_id, group_ids=group_ids, page=page, page_size=page_size
        )
        return {
            "items": [self._user_projection(notification, is_dismissed) for notification, is_dismissed in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def get_history_detail(self, *, user_id: UUID, notification_id: UUID) -> dict[str, Any]:
        """返回当前用户历史上可见的单条通知详情，不可见时按不存在处理。"""

        group_ids = _resolve_audience(self._session, user_id)
        notification = self._crud.get_history(
            notification_id=notification_id, user_id=user_id, group_ids=group_ids
        )
        if notification is None:
            raise NotFoundError("通知不存在")
        is_dismissed = self._crud.is_dismissed(user_id=user_id, notification_id=notification_id)
        return self._user_projection(notification, is_dismissed)

    def pending_count(self, *, user_id: UUID) -> int:
        """返回当前用户可见且未关闭的生效中通知数量。"""

        group_ids = _resolve_audience(self._session, user_id)
        return self._crud.count_pending(user_id=user_id, group_ids=group_ids)

    def dismiss(self, *, user_id: UUID, notification_id: UUID) -> dict[str, Any]:
        """关闭一条对当前用户可见的通知，避免其再次弹窗。"""

        group_ids = _resolve_audience(self._session, user_id)
        notification = self._crud.get_history(
            notification_id=notification_id, user_id=user_id, group_ids=group_ids
        )
        if notification is None:
            raise NotFoundError("通知不存在")
        try:
            self._crud.dismiss(user_id=user_id, notification_id=notification_id, dismissed_at=datetime.now(UTC))
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
        return {"success": True}

    @staticmethod
    def _user_projection(notification: Notification, is_dismissed: bool) -> dict[str, Any]:
        return {
            "id": notification.id,
            "title": notification.title,
            "content": notification.content,
            "start_at": notification.start_at,
            "expires_at": notification.expires_at,
            "created_at": notification.created_at,
            "is_dismissed": is_dismissed,
        }


class InboxService:
    """编排统一收件箱列表与详情，按 category 分派到消息或通知用例。"""

    def __init__(self, session: Session) -> None:
        """绑定请求级事务会话并初始化消息与通知服务。"""

        self._messages = MessageService(session)
        self._notifications = NotificationService(session)

    def list_page(
        self,
        *,
        user_id: UUID,
        category: InboxCategory,
        message_type: MessageType | None,
        unread_only: bool,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        """按类别返回消息或历史通知的统一列表结果。"""

        if category is InboxCategory.notification:
            result = self._notifications.list_history_page(user_id=user_id, page=page, page_size=page_size)
        else:
            result = self._messages.list_page(
                user_id=user_id,
                message_type=message_type,
                unread_only=unread_only,
                page=page,
                page_size=page_size,
            )
        return {"category": category.value, **result}

    def get_detail(self, *, user_id: UUID, category: InboxCategory, target_id: UUID) -> dict[str, Any]:
        """按类别返回消息或历史通知的详情。"""

        if category is InboxCategory.notification:
            result = self._notifications.get_history_detail(user_id=user_id, notification_id=target_id)
        else:
            result = self._messages.get_detail(user_id=user_id, message_id=target_id)
        return {"category": category.value, **result}

    def unread_counts(self, *, user_id: UUID) -> dict[str, Any]:
        """返回消息未读数与通知待处理数，供前端 tab 角标使用。"""

        return {
            "message_unread_count": self._messages.unread_count(user_id=user_id),
            "notification_pending_count": self._notifications.pending_count(user_id=user_id),
        }
