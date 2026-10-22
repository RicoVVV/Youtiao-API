"""用户资料 HTTP API，仅提供当前已认证账号的安全信息。"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.core.auth import get_user_id
from app.core.database import get_db
from app.modules.user.api.profile.schemas import (
    BalanceAlertSettingsResponse,
    BalanceAlertUpdateRequest,
)
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
        "email": profile.email,
        "balance_alert_threshold": profile.balance_alert_threshold,
        "balance_alert_email": profile.balance_alert_email,
        "created_at": profile.created_at,
        "membership": profile.membership,
    }


@router.post(
    "/balance-alert/update",
    response_model=BalanceAlertSettingsResponse,
    summary="更新用户余额预警设置",
)
def update_balance_alert_settings(
    payload: BalanceAlertUpdateRequest,
    user_id: Annotated[UUID, Depends(get_user_id)],
    session: Annotated[Session, Depends(get_db)],
) -> dict[str, str | None]:
    """设置或清除当前用户的余额预警阈值与收件邮箱。

    参数：threshold 为正数阈值，传 null 关闭余额预警；email 留空时使用注册邮箱。
    返回值：更新后的阈值与自设邮箱，未设置时为 null。
    异常：阈值非正数、邮箱格式不合法，或未绑定邮箱且未填写收件邮箱时返回 422。
    """

    return UserProfileApplicationService(session).update_balance_alert_settings(user_id=user_id, **payload.model_dump())
