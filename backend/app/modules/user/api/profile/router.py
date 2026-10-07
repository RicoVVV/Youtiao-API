"""用户资料 HTTP API，仅提供当前已认证账号的安全信息。"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.core.auth import get_user_id
from app.core.database import get_db
from app.modules.user.application.profile.services import UserProfileApplicationService

router = APIRouter(prefix="/user", tags=["用户资料"])


@router.get("/info", summary="查询当前用户信息")
def get_user_info(user_id: Annotated[UUID, Depends(get_user_id)], session: Annotated[Session, Depends(get_db)]) -> dict:
    """返回当前 JWT 用户的基础账号状态。

    参数：user_id 为已鉴权的用户标识，session 为当前请求数据库会话。
    返回值：不含密码和认证凭据的用户账号投影。
    异常：用户在鉴权完成后被删除时返回 HTTP 401。
    """

    profile = UserProfileApplicationService(session).get_profile(user_id)
    return {
        "id": str(profile.id),
        "username": profile.username,
        "is_active": profile.is_active,
        "is_admin": profile.is_admin,
        "balance": profile.balance,
        "usage": profile.usage,
        "created_at": profile.created_at,
    }
