"""管理员使用记录 HTTP 接口。"""

from typing import Annotated
from uuid import UUID

from app.core.auth import get_admin_user_id
from app.core.database import get_db
from app.modules.usage.api.schemas import (
    AdminUsageRecordListQuery,
    AdminUsageStatisticsQuery,
    UsageRecordDetailQuery,
    UsageStatisticsDimensionQuery,
    usage_record_response,
)
from app.modules.usage.application.services import UsageApplicationService
from app.modules.usage.application.statistics_services import UsageStatisticsApplicationService
from fastapi import APIRouter, Depends
from sqlmodel import Session

router = APIRouter(prefix="/usage", tags=["管理员使用记录"])


@router.get("/records/list", summary="查询全部使用记录")
def list_usage_records(
    payload: Annotated[AdminUsageRecordListQuery, Depends()],
    _: Annotated[UUID, Depends(get_admin_user_id)],
    session: Annotated[Session, Depends(get_db)],
) -> dict:
    total, items = UsageApplicationService(session).list_admin(**payload.model_dump())
    return {
        "items": [usage_record_response(item, detail=False, include_admin_fields=True) for item in items],
        "total": total,
        "page": payload.page,
        "page_size": payload.page_size,
    }


@router.get("/records/detail", summary="查询使用记录详情")
def usage_record_detail(
    payload: Annotated[UsageRecordDetailQuery, Depends()],
    _: Annotated[UUID, Depends(get_admin_user_id)],
    session: Annotated[Session, Depends(get_db)],
) -> dict:
    record = UsageApplicationService(session).get(payload.usage_record_id)
    return usage_record_response(record, detail=True, include_admin_fields=True)


@router.get("/statistics/overview", summary="查询全部用量概览")
def usage_statistics_overview(
    payload: Annotated[AdminUsageStatisticsQuery, Depends()],
    _: Annotated[UUID, Depends(get_admin_user_id)],
    session: Annotated[Session, Depends(get_db)],
) -> dict:
    return UsageStatisticsApplicationService(session).overview(
        filters=payload.model_dump(exclude={"range", "start_at", "end_at"}),
        range_name=payload.range,
        start_at=payload.start_at,
        end_at=payload.end_at,
    )


@router.get("/statistics/trend", summary="查询全部用量趋势")
def usage_statistics_trend(
    payload: Annotated[AdminUsageStatisticsQuery, Depends()],
    _: Annotated[UUID, Depends(get_admin_user_id)],
    session: Annotated[Session, Depends(get_db)],
) -> dict:
    return {
        "items": UsageStatisticsApplicationService(session).trend(
            filters=payload.model_dump(exclude={"range", "start_at", "end_at"}),
            range_name=payload.range,
            start_at=payload.start_at,
            end_at=payload.end_at,
        )
    }


@router.get("/statistics/dimensions/list", summary="查询用量维度分布")
def usage_statistics_dimensions(
    payload: Annotated[UsageStatisticsDimensionQuery, Depends()],
    _: Annotated[UUID, Depends(get_admin_user_id)],
    session: Annotated[Session, Depends(get_db)],
) -> dict:
    total, items = UsageStatisticsApplicationService(session).dimensions(
        dimension=payload.dimension,
        filters=payload.model_dump(exclude={"range", "start_at", "end_at", "dimension", "page", "page_size"}),
        range_name=payload.range,
        start_at=payload.start_at,
        end_at=payload.end_at,
        page=payload.page,
        page_size=payload.page_size,
    )
    return {"items": items, "total": total, "page": payload.page, "page_size": payload.page_size}
