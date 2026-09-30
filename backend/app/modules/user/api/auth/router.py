"""认证 HTTP API，负责请求解析、响应映射和认证 Cookie 适配。"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, Request, Response
from sqlmodel import Session

from app.core.auth import enforce_login_rate_limit, enforce_refresh_rate_limit, get_user_id
from app.core.config import get_settings
from app.core.database import get_db
from app.modules.user.api.auth.schemas import (
    Credentials,
    EmailVerificationCodeRequest,
    SetupStatusResponse,
    UserRegisterRequest,
    UserRegistrationRequest,
)
from app.modules.user.application.auth.email_verification import EmailVerificationService
from app.modules.user.application.auth.services import AuthApplicationService

router = APIRouter(prefix="/auth", tags=["认证"])


def _set_auth_cookies(response: Response, refresh: str) -> None:
    """仅写入 HttpOnly refresh Cookie，并禁止认证响应被缓存。"""

    settings = get_settings()
    cookie_options = {
        "httponly": True,
        "secure": settings.auth_cookie_secure,
        "samesite": settings.auth_cookie_samesite,
        "domain": settings.auth_cookie_domain,
    }
    response.set_cookie(
        "refresh_token", refresh, path="/api/auth", max_age=settings.refresh_token_days * 86400, **cookie_options
    )
    response.headers["Cache-Control"] = "no-store"


@router.get("/setup-status", response_model=SetupStatusResponse, summary="读取首次安装状态")
def get_setup_status(session: Annotated[Session, Depends(get_db)]) -> SetupStatusResponse:
    """返回首次管理员是否尚未创建，前端据此显示初始化或登录页面。"""

    return SetupStatusResponse(setup_required=AuthApplicationService(session).is_setup_required())


@router.post("/setup-admin", response_model=None, summary="创建首次管理员")
def setup_initial_admin(
    payload: UserRegistrationRequest,
    response: Response,
    session: Annotated[Session, Depends(get_db)],
    request: Request,
) -> dict:
    """创建首次管理员后立即签发认证令牌，使前端无需再次提交密码即可进入后台。"""

    service = AuthApplicationService(session)
    service.setup_initial_admin(**payload.model_dump())
    client_host = request.client.host if request.client else "unknown"
    tokens = service.login(**payload.model_dump(), client_host=client_host)
    _set_auth_cookies(response, tokens.refresh_token)
    return {"access_token": tokens.access_token}


@router.post("/register", response_model=None, summary="注册用户")
def register_user(payload: UserRegisterRequest, session: Annotated[Session, Depends(get_db)]) -> None:
    """公开注册用户并创建初始钱包。

    参数：payload 包含用户名、密码，以及开启邮箱验证时必填的邮箱和验证码。
    返回值：无；成功响应由统一响应信封表示。
    异常：用户名或邮箱重复时返回 409，验证码缺失或错误时返回 422，事务由应用服务负责。
    """

    AuthApplicationService(session).register_user(**payload.model_dump())
    return None


@router.post("/email-verification-codes/send", response_model=None, summary="发送注册邮箱验证码")
def send_email_verification_code(
    payload: EmailVerificationCodeRequest,
    session: Annotated[Session, Depends(get_db)],
    request: Request,
) -> None:
    """向待注册邮箱发送 6 位验证码；功能未开启返回 422，邮箱已注册返回 409，限流或冷却返回 429。"""

    client_host = request.client.host if request.client else "unknown"
    EmailVerificationService(session, get_settings()).send_registration_code(
        **payload.model_dump(), client_host=client_host
    )
    return None


@router.post("/login", summary="用户登录")
def login(
    payload: Credentials, response: Response, session: Annotated[Session, Depends(get_db)], request: Request = None
) -> dict:
    """用户密码登录，返回短期 access JWT 并写入 refresh Cookie。"""

    client_host = request.client.host if request is not None and request.client else "unknown"
    enforce_login_rate_limit(client_host)
    tokens = AuthApplicationService(session).login(**payload.model_dump(), client_host=client_host)
    _set_auth_cookies(response, tokens.refresh_token)
    return {"access_token": tokens.access_token}


@router.post("/refresh", summary="刷新访问令牌")
def refresh(
    response: Response,
    session: Annotated[Session, Depends(get_db)],
    refresh_cookie: Annotated[str | None, Cookie(alias="refresh_token")] = None,
    request: Request = None,
) -> dict:
    """仅从 HttpOnly Cookie 读取刷新令牌并完成轮换。"""

    client_host = request.client.host if request is not None and request.client else "unknown"
    enforce_refresh_rate_limit(client_host)
    tokens = AuthApplicationService(session).refresh(raw_refresh=refresh_cookie, client_host=client_host)
    _set_auth_cookies(response, tokens.refresh_token)
    return {"access_token": tokens.access_token}


@router.post("/logout", summary="退出当前登录会话")
def logout(
    user_id: Annotated[UUID, Depends(get_user_id)],
    request: Request,
    session: Annotated[Session, Depends(get_db)],
    response: Response,
) -> None:
    """仅撤销当前 JWT 指向的会话，不影响用户其他设备。"""

    AuthApplicationService(session).logout(user_id=user_id, auth_session_id=request.state.session_id)
    response.delete_cookie("refresh_token", path="/api/auth", domain=get_settings().auth_cookie_domain)
    response.headers["Cache-Control"] = "no-store"
    return {}
