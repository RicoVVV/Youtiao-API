"""长期 Token HTTP API，负责用户自助凭证生命周期。"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.core.auth import get_user_id
from app.core.database import get_db
from app.modules.user.api.token.schemas import (
    TokenCopyResponse,
    TokenDeletionRequest,
    TokenGroupItem,
    TokenGroupsUpdateRequest,
    TokenListItem,
    TokenListResponse,
    TokenRequest,
    TokenViewResponse,
)
from app.modules.user.application.token.services import TokenApplicationService

router = APIRouter(prefix="/user", tags=["用户访问令牌"])


@router.get("/token/list", response_model=TokenListResponse, summary="分页查询 Token 列表")
def list_tokens(
    user_id: Annotated[UUID, Depends(get_user_id)],
    session: Annotated[Session, Depends(get_db)],
    page: int = Query(default=1, ge=1, description="从 1 开始的页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="单页最大返回 100 条"),
) -> TokenListResponse:
    """分页返回当前用户长期 Token 的非敏感展示信息。"""

    result = TokenApplicationService(session).list_tokens_page(user_id, page, page_size)
    return TokenListResponse(
        items=[TokenListItem.model_validate(item, from_attributes=True) for item in result.tokens],
        total=result.total,
        page=page,
        page_size=page_size,
    )


@router.get("/token/copy", response_model=TokenCopyResponse, summary="复制 Token")
def copy_token(
    user_id: Annotated[UUID, Depends(get_user_id)],
    session: Annotated[Session, Depends(get_db)],
    token_id: Annotated[UUID, Query(description="待复制的 Token 标识")],
) -> TokenCopyResponse:
    token = TokenApplicationService(session).copy_token(user_id, token_id)
    return TokenCopyResponse(token_id=token_id, token=token)


@router.post("/token/create", summary="创建 Token")
def create_token(
    payload: TokenRequest,
    user_id: Annotated[UUID, Depends(get_user_id)],
    session: Annotated[Session, Depends(get_db)],
) -> TokenViewResponse:
    """为当前用户签发并保存新的长期 Token。"""

    return TokenViewResponse.model_validate(
        TokenApplicationService(session).create_token(user_id=user_id, **payload.model_dump()), from_attributes=True
    )


@router.post("/token/delete", summary="软删除 Token")
def delete_token(
    payload: TokenDeletionRequest,
    user_id: Annotated[UUID, Depends(get_user_id)],
    session: Annotated[Session, Depends(get_db)],
) -> TokenViewResponse:
    """软删除请求体中指定且归属当前用户的长期 Token。"""

    return TokenViewResponse.model_validate(
        TokenApplicationService(session).delete_token(user_id, payload.token_id), from_attributes=True
    )


@router.post("/token/disable", summary="禁用 Token")
def disable_token(
    payload: TokenDeletionRequest,
    user_id: Annotated[UUID, Depends(get_user_id)],
    session: Annotated[Session, Depends(get_db)],
) -> TokenViewResponse:
    """禁用当前用户的 Token，保留记录并允许后续重新启用。"""

    return TokenViewResponse.model_validate(
        TokenApplicationService(session).set_token_active(user_id, payload.token_id, False), from_attributes=True
    )


@router.post("/token/enable", summary="启用 Token")
def enable_token(
    payload: TokenDeletionRequest,
    user_id: Annotated[UUID, Depends(get_user_id)],
    session: Annotated[Session, Depends(get_db)],
) -> TokenViewResponse:
    """启用当前用户仍保留的 Token，软删除记录不会出现在查询结果中。"""

    return TokenViewResponse.model_validate(
        TokenApplicationService(session).set_token_active(user_id, payload.token_id, True), from_attributes=True
    )


@router.get("/token/group/list", response_model=list[TokenGroupItem], summary="查询可选 Token 分组")
def list_available_groups(
    user_id: Annotated[UUID, Depends(get_user_id)], session: Annotated[Session, Depends(get_db)]
) -> list[TokenGroupItem]:
    """返回当前用户可绑定的全部启用分组，不暴露其他用户授权信息。"""

    return [
        TokenGroupItem.model_validate(item, from_attributes=True)
        for item in TokenApplicationService(session).list_available_groups(user_id)
    ]


@router.post("/token/groups/update", summary="更新 Token 分组绑定")
def update_token_groups(
    payload: TokenGroupsUpdateRequest,
    user_id: Annotated[UUID, Depends(get_user_id)],
    session: Annotated[Session, Depends(get_db)],
) -> TokenViewResponse:
    """整体替换当前用户 Token 的有序分组绑定。"""

    return TokenViewResponse.model_validate(
        TokenApplicationService(session).replace_token_groups(user_id=user_id, **payload.model_dump()),
        from_attributes=True,
    )
