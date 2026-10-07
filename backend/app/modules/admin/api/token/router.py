"""管理员长期 Token HTTP API，负责为指定用户签发额外凭证。"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.core.auth import get_admin_user_id
from app.core.database import get_db
from app.modules.admin.api.token.schemas import AdminTokenResponse, AdminUserTokenRequest
from app.modules.user.application.token.services import TokenApplicationService

router = APIRouter(prefix="/admin/user/token", tags=["管理员用户与令牌"])


@router.post(
    "/create", response_model=AdminTokenResponse, dependencies=[Depends(get_admin_user_id)], summary="为用户创建 Token"
)
def create_user_token(
    payload: AdminUserTokenRequest, session: Annotated[Session, Depends(get_db)]
) -> AdminTokenResponse:
    token, secret = TokenApplicationService(session).issue_token_for_existing_user(**payload.model_dump())
    return AdminTokenResponse(id=token.id, user_id=token.user_id, key_prefix=token.key_prefix, token=secret.raw_value)
