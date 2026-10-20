"""用户概览 RPC HTTP API。

本模块只处理用户鉴权、请求校验与响应组装；聚合规则由应用服务负责。
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.core.auth import get_user_id
from app.core.database import get_db
from app.modules.overview.api.schemas import OverviewQuery
from app.modules.overview.application.services import OverviewApplicationService

router = APIRouter(prefix="/overview", tags=["概览"])


@router.get("/detail", summary="查询用户概览")
def get_user_overview(
    payload: Annotated[OverviewQuery, Depends()],
    user_id: Annotated[UUID, Depends(get_user_id)],
    session: Annotated[Session, Depends(get_db)],
) -> dict:
    return OverviewApplicationService(session).user_overview(
        user_id=user_id,
        message_page=payload.message_page,
        message_page_size=payload.message_page_size,
    )
