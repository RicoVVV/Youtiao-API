"""消息与通知数据访问层。"""

from app.modules.message.crud.message_crud import MessageCrud
from app.modules.message.crud.notification_crud import NotificationCrud

__all__ = ["MessageCrud", "NotificationCrud"]
