"""FastAPI 进程入口，负责装配 HTTP 路由与应用级基础设施。"""

# ruff: noqa: E402

import sys
from pathlib import Path

# IDEA 直接执行 app/main.py 时仅会将 app 目录加入搜索路径，需要补充 backend 包根目录以支持 app.* 绝对导入。
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from fastapi import FastAPI

from app.bootstrap.api import register_api_routes
from app.bootstrap.lifespan import lifespan
from app.bootstrap.middleware import register_middleware
from app.bootstrap.route_tags import ROUTE_TAGS
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.modules.payment.api.exception_handlers import register_payment_exception_handlers
from app.web.exception_handlers import register_exception_handlers
from app.web.request_context import RequestContextMiddleware

configure_logging()
settings = get_settings()

app = FastAPI(
    title="Youtiao API",
    version="0.1.0",
    lifespan=lifespan,
    docs_url=None if settings.is_production else "/api/docs",
    openapi_url=None if settings.is_production else "/api/openapi.json",
    redoc_url=None if settings.is_production else "/api/redoc",
    openapi_tags=ROUTE_TAGS,
)

register_middleware(app)
app.add_middleware(RequestContextMiddleware)
register_exception_handlers(app)
register_payment_exception_handlers(app)
register_api_routes(app)


if __name__ == "__main__":
    import uvicorn

    from app.bootstrap.startup import run_database_migrations

    run_database_migrations()
    uvicorn.run("app.main:app", host="0.0.0.0", port=3000, log_config=None)
