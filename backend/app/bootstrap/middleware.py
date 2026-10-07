"""应用级中间件装配。"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


def register_middleware(app: FastAPI) -> None:
    """注册应用中间件。"""

    # 跨域放行全部来源：用正则匹配任意 Origin（而非字面 "*"），
    # 这样在 allow_credentials=True 时仍会正确回显请求来源并允许携带 Cookie。
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=".*",
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )
