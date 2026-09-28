"""HTTP 路由组合根，统一注册各领域公开接口。"""

from fastapi import FastAPI

from app.bootstrap.health import router as health_router
from app.modules.admin.router import router as admin_router
from app.modules.api_docs.api.router import router as api_docs_router
from app.modules.billing.api.router import router as billing_router
from app.modules.generation.api.router import router as generation_router
from app.modules.marketplace.api.router import router as model_marketplace_router
from app.modules.monitoring.api.router import router as monitoring_router
from app.modules.payment.api.payment.router import router as payment_router
from app.modules.providers.api.router import router as providers_router
from app.modules.system_settings.api import router as system_settings_router
from app.modules.usage.api.router import router as usage_router
from app.modules.user.api.auth.router import router as auth_router
from app.modules.user.api.profile.router import router as user_profile_router
from app.modules.user.api.token.router import router as token_router
from app.modules.video.api.router import router as video_router
from app.modules.wallet.api.router import router as wallet_router


def register_api_routes(app: FastAPI) -> None:
    """向 FastAPI 应用注册领域路由。

    参数：app 为待装配的 FastAPI 应用实例。
    返回值：无。
    副作用：为应用增加身份、计费、支付、视频和管理员接口。
    """

    app.include_router(health_router, prefix="/api")
    app.include_router(api_docs_router, prefix="/api")
    app.include_router(video_router)
    app.include_router(generation_router)
    app.include_router(model_marketplace_router, prefix="/api")
    app.include_router(monitoring_router, prefix="/api")
    app.include_router(providers_router, prefix="/api")
    app.include_router(admin_router, prefix="/api")
    app.include_router(auth_router, prefix="/api")
    app.include_router(user_profile_router, prefix="/api")
    app.include_router(token_router, prefix="/api")
    app.include_router(usage_router, prefix="/api")
    app.include_router(billing_router, prefix="/api")
    app.include_router(wallet_router, prefix="/api")
    app.include_router(payment_router, prefix="/api")
    app.include_router(system_settings_router, prefix="/api")
