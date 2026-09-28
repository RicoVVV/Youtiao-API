"""用户侧分组监控 HTTP 接口。"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.core.auth import get_user_id
from app.core.database import get_db
from app.modules.monitoring.api.schemas import GroupMonitorListQuery, GroupMonitorTrendQuery
from app.modules.monitoring.application.query_services import GroupMonitorQueryApplicationService

router = APIRouter(prefix="/monitoring", tags=["分组监控"])


@router.get("/groups/list", summary="查询可用分组监控指标")
def list_group_metrics(
    payload: Annotated[GroupMonitorListQuery, Depends()],
    user_id: Annotated[UUID, Depends(get_user_id)],
    session: Annotated[Session, Depends(get_db)],
) -> dict:
    return GroupMonitorQueryApplicationService(session).user_group_metrics(user_id=user_id, group_id=payload.group_id)


@router.get("/groups/trend", summary="查询分组监控指标趋势")
def group_metrics_trend(
    payload: Annotated[GroupMonitorTrendQuery, Depends()],
    user_id: Annotated[UUID, Depends(get_user_id)],
    session: Annotated[Session, Depends(get_db)],
) -> dict:
    return GroupMonitorQueryApplicationService(session).group_trend(
        group_id=payload.group_id,
        request_type=payload.request_type,
        hours=payload.hours,
        user_id=user_id,
    )
