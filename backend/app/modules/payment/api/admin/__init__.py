"""管理员支付配置 HTTP API 包。"""

from app.modules.payment.application.admin.settings import PaymentSettingsService

from .router import router

__all__ = ["router", "PaymentSettingsService"]
