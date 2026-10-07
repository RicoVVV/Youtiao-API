"""用户使用记录 HTTP 接口。"""

from typing import Annotated
from uuid import UUID

from app.core.auth import get_user_id
from app.core.database import get_db
from app.modules.usage.api.schemas import (
    UsageRecordDetailQuery,
    UsageRecordListQuery,
    UsageStatisticsModelsQuery,
    UsageStatisticsQuery,
    usage_record_response,
)
from app.modules.usage.application.services import UsageApplicationService
from app.modules.usage.application.statistics_services import UsageStatisticsApplicationService
from fastapi import APIRouter, Depends
from sqlmodel import Session

router = APIRouter(prefix="/usage", tags=["使用记录"])


@router.get("/records/list", summary="查询我的使用记录")
def list_usage_records(
    payload: Annotated[UsageRecordListQuery, Depends()],
    user_id: Annotated[UUID, Depends(get_user_id)],
    session: Annotated[Session, Depends(get_db)],
) -> dict:
    total, items = UsageApplicationService(session).list_owned(user_id=user_id, **payload.model_dump())
    return {
        "items": [usage_record_response(item, detail=False, include_admin_fields=False) for item in items],
        "total": total,
        "page": payload.page,
        "page_size": payload.page_size,
    }


@router.get("/records/detail", summary="查询我的使用记录详情")
def usage_record_detail(
    payload: Annotated[UsageRecordDetailQuery, Depends()],
    user_id: Annotated[UUID, Depends(get_user_id)],
    session: Annotated[Session, Depends(get_db)],
) -> dict:
    record = UsageApplicationService(session).get_owned(usage_record_id=payload.usage_record_id, user_id=user_id)
    return usage_record_response(record, detail=True, include_admin_fields=False)


@router.get("/statistics/overview", summary="查询我的用量概览")
def usage_statistics_overview(
    payload: Annotated[UsageStatisticsQuery, Depends()],
    user_id: Annotated[UUID, Depends(get_user_id)],
    session: Annotated[Session, Depends(get_db)],
) -> dict:
    return UsageStatisticsApplicationService(session).overview(
        filters={**payload.model_dump(exclude={"range", "start_at", "end_at"}), "user_id": user_id},
        range_name=payload.range,
        start_at=payload.start_at,
        end_at=payload.end_at,
    )


@router.get("/statistics/trend", summary="查询我的用量趋势")
def usage_statistics_trend(
    payload: Annotated[UsageStatisticsQuery, Depends()],
    user_id: Annotated[UUID, Depends(get_user_id)],
    session: Annotated[Session, Depends(get_db)],
) -> dict:
    return {
        "items": UsageStatisticsApplicationService(session).trend(
            filters={**payload.model_dump(exclude={"range", "start_at", "end_at"}), "user_id": user_id},
            range_name=payload.range,
            start_at=payload.start_at,
            end_at=payload.end_at,
        )
    }


@router.get("/statistics/models/list", summary="查询我的模型用量分布")
def usage_statistics_models(
    payload: Annotated[UsageStatisticsModelsQuery, Depends()],
    user_id: Annotated[UUID, Depends(get_user_id)],
    session: Annotated[Session, Depends(get_db)],
) -> dict:
    total, items = UsageStatisticsApplicationService(session).dimensions(
        dimension="model",
        filters={
            **payload.model_dump(exclude={"range", "start_at", "end_at", "page", "page_size"}),
            "user_id": user_id,
        },
        range_name=payload.range,
        start_at=payload.start_at,
        end_at=payload.end_at,
        page=payload.page,
        page_size=payload.page_size,
    )
    return {"items": items, "total": total, "page": payload.page, "page_size": payload.page_size}
