"""管理员站点信息 RPC HTTP API。

本模块只处理管理员鉴权、请求校验与响应组装；站点信息维护规则由应用服务负责。
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.core.auth import get_admin_user_id
from app.core.database import get_db
from app.modules.site_info.api.schemas import (
    AdminSiteInfoCreateRequest,
    AdminSiteInfoDeleteRequest,
    AdminSiteInfoListResponse,
    AdminSiteInfoResponse,
    AdminSiteInfoStatusRequest,
    AdminSiteInfoUpdateRequest,
)
from app.modules.site_info.application.services import SiteInfoApplicationService

admin_router = APIRouter(prefix="/admin/site-info", tags=["管理员站点信息"])


@admin_router.get(
    "/list",
    response_model=AdminSiteInfoListResponse,
    dependencies=[Depends(get_admin_user_id)],
    summary="查询站点信息列表",
)
def list_site_infos(
    session: Annotated[Session, Depends(get_db)],
    keyword: Annotated[str | None, Query(max_length=255)] = None,
    is_active: Annotated[bool | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict:
    return SiteInfoApplicationService(session).list_page(
        keyword=keyword, is_active=is_active, page=page, page_size=page_size
    )


@admin_router.get(
    "/detail",
    response_model=AdminSiteInfoResponse,
    dependencies=[Depends(get_admin_user_id)],
    summary="查询站点信息详情",
)
def get_site_info_detail(session: Annotated[Session, Depends(get_db)], site_info_id: Annotated[UUID, Query()]) -> dict:
    return SiteInfoApplicationService(session).get_detail(site_info_id)


@admin_router.post(
    "/create",
    response_model=AdminSiteInfoResponse,
    dependencies=[Depends(get_admin_user_id)],
    summary="创建站点信息",
)
def create_site_info(payload: AdminSiteInfoCreateRequest, session: Annotated[Session, Depends(get_db)]) -> dict:
    return SiteInfoApplicationService(session).create(payload.model_dump())


@admin_router.post(
    "/update",
    response_model=AdminSiteInfoResponse,
    dependencies=[Depends(get_admin_user_id)],
    summary="更新站点信息",
)
def update_site_info(payload: AdminSiteInfoUpdateRequest, session: Annotated[Session, Depends(get_db)]) -> dict:
    return SiteInfoApplicationService(session).update(payload.model_dump(exclude_unset=True))


@admin_router.post(
    "/update-status",
    response_model=AdminSiteInfoResponse,
    dependencies=[Depends(get_admin_user_id)],
    summary="更新站点信息状态",
)
def update_site_info_status(payload: AdminSiteInfoStatusRequest, session: Annotated[Session, Depends(get_db)]) -> dict:
    return SiteInfoApplicationService(session).update_status(**payload.model_dump())


@admin_router.post(
    "/delete",
    dependencies=[Depends(get_admin_user_id)],
    summary="删除站点信息",
)
def delete_site_info(payload: AdminSiteInfoDeleteRequest, session: Annotated[Session, Depends(get_db)]) -> dict:
    SiteInfoApplicationService(session).delete(payload.site_info_id)
    return {"success": True}
