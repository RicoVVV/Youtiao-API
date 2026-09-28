"""管理员 API 聚合入口，仅组合按业务拆分的子路由。

本模块不承载请求 DTO、业务编排、数据库访问或事务处理；具体接口由所属子路由调用应用服务完成。
"""

from fastapi import APIRouter

from app.modules.admin.api.billing.router import router as billing_router
from app.modules.admin.api.channels.router import router as channels_router
from app.modules.admin.api.concurrency.router import router as user_concurrency_router
from app.modules.admin.api.models.router import router as models_router
from app.modules.admin.api.monitoring.router import router as monitoring_router
from app.modules.admin.api.pricing_modifiers.router import router as pricing_modifiers_router
from app.modules.admin.api.pricing_rules.router import router as pricing_rules_router
from app.modules.admin.api.provider_templates.router import router as provider_templates_router
from app.modules.admin.api.token.groups.router import router as token_groups_router
from app.modules.admin.api.token.router import router as token_router
from app.modules.admin.api.usage.router import router as usage_router
from app.modules.admin.api.users.router import router as users_router
from app.modules.admin.api.videos.router import router as videos_router
from app.modules.payment.api.admin.router import router as payment_router
from app.modules.system_settings.api import admin_router as system_settings_router

router = APIRouter()
router.include_router(users_router)
router.include_router(usage_router, prefix="/admin")
router.include_router(token_router)
router.include_router(token_groups_router)
router.include_router(videos_router, prefix="/admin")
router.include_router(channels_router, prefix="/admin")
router.include_router(billing_router, prefix="/admin")
router.include_router(models_router, prefix="/admin")
router.include_router(monitoring_router, prefix="/admin")
router.include_router(pricing_rules_router, prefix="/admin")
router.include_router(pricing_modifiers_router, prefix="/admin")
router.include_router(provider_templates_router, prefix="/admin")
router.include_router(user_concurrency_router, prefix="/admin")
router.include_router(payment_router)
router.include_router(system_settings_router)
