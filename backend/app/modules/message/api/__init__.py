"""用户端消息与通知 API 层入口。"""

from app.modules.message.api.notification_router import router as notification_router
from app.modules.message.api.router import router as message_router

__all__ = ["message_router", "notification_router"]
