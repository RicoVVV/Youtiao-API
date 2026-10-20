"""用户端消息与通知 RPC API 的请求与响应契约。

本模块仅定义用户端接口的数据校验规则，不包含鉴权、事务或业务编排。
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.modules.message.application.services import InboxCategory
from app.modules.message.model import MessageType


class InboxMessageItem(BaseModel):
    """描述统一收件箱中的一条消息。"""

    id: UUID
    title: str
    content: str
    type: MessageType
    start_at: datetime
    expires_at: datetime | None
    created_at: datetime | None
    is_read: bool


class InboxNotificationItem(BaseModel):
    """描述统一收件箱中的一条历史通知。"""

    id: UUID
    title: str
    content: str
    start_at: datetime
    expires_at: datetime | None
    created_at: datetime | None
    is_dismissed: bool


class InboxListResponse(BaseModel):
    """描述统一收件箱分页结果，items 形状由 category 决定。"""

    category: InboxCategory
    items: list[InboxMessageItem] | list[InboxNotificationItem]
    total: int
    page: int
    page_size: int


class InboxMessageDetail(BaseModel):
    """描述统一收件箱中一条消息的详情。"""

    category: InboxCategory
    id: UUID
    title: str
    content: str
    type: MessageType
    start_at: datetime
    expires_at: datetime | None
    created_at: datetime | None
    is_read: bool


class InboxNotificationDetail(BaseModel):
    """描述统一收件箱中一条历史通知的详情。"""

    category: InboxCategory
    id: UUID
    title: str
    content: str
    start_at: datetime
    expires_at: datetime | None
    created_at: datetime | None
    is_dismissed: bool


class InboxUnreadCountResponse(BaseModel):
    """描述消息未读数与通知待处理数，供前端 tab 角标使用。"""

    message_unread_count: int
    notification_pending_count: int


class MessageReadRequest(BaseModel):
    """描述用户标记单条消息已读时提交的消息标识。"""

    message_id: UUID


class MessageMarkReadResponse(BaseModel):
    """描述用户端标记单条消息已读的结果。"""

    success: bool


class MessageMarkAllReadResponse(BaseModel):
    """描述用户端消息全部标记已读的结果。"""

    marked_count: int


class NotificationCurrentResponse(BaseModel):
    """描述当前弹窗通知，无生效中或已被关闭时为 null。"""

    notification: InboxNotificationItem | None


class NotificationDismissRequest(BaseModel):
    """描述用户关闭单条通知时提交的通知标识。"""

    notification_id: UUID
