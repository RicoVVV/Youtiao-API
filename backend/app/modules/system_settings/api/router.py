from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.core.auth import get_admin_user_id
from app.core.config import get_settings
from app.core.database import get_db
from app.modules.system_settings.api.schemas import (
    AdminSidebarModulesResponse,
    AdminSystemSettingsResponse,
    SidebarModulesResponse,
    SidebarModulesUpdateRequest,
    SystemSettingsResponse,
    SystemSettingsUpdateRequest,
)
from app.modules.system_settings.application.services import SystemSettingsApplicationService

router = APIRouter(prefix="/system-settings", tags=["系统设置"])
admin_router = APIRouter(prefix="/admin/system-settings", tags=["管理员系统设置"])


@router.get("/detail", response_model=SystemSettingsResponse, summary="查询公开系统设置")
def get_public_system_settings(session: Annotated[Session, Depends(get_db)]) -> dict[str, Any]:
    return SystemSettingsApplicationService(session, get_settings()).get_public_settings()


@admin_router.get(
    "/detail",
    response_model=AdminSystemSettingsResponse,
    dependencies=[Depends(get_admin_user_id)],
    summary="查询管理员系统设置",
)
def get_admin_system_settings(session: Annotated[Session, Depends(get_db)]) -> dict[str, Any]:
    return SystemSettingsApplicationService(session, get_settings()).get_admin_settings()


@admin_router.post(
    "/update",
    response_model=AdminSystemSettingsResponse,
    dependencies=[Depends(get_admin_user_id)],
    summary="更新管理员系统设置",
)
def update_admin_system_settings(
    payload: SystemSettingsUpdateRequest, session: Annotated[Session, Depends(get_db)]
) -> dict[str, Any]:
    return SystemSettingsApplicationService(session, get_settings()).update_admin_settings(
        payload.model_dump(exclude_unset=True)
    )


@router.get(
    "/sidebar-modules/detail",
    response_model=SidebarModulesResponse,
    summary="查询控制台侧边栏可见模块",
)
def get_sidebar_modules(session: Annotated[Session, Depends(get_db)]) -> dict[str, Any]:
    return SystemSettingsApplicationService(session, get_settings()).get_sidebar_modules()


@admin_router.get(
    "/sidebar-modules/detail",
    response_model=AdminSidebarModulesResponse,
    dependencies=[Depends(get_admin_user_id)],
    summary="查询管理员侧边栏模块配置",
)
def get_admin_sidebar_modules(session: Annotated[Session, Depends(get_db)]) -> dict[str, Any]:
    return SystemSettingsApplicationService(session, get_settings()).get_admin_sidebar_modules()


@admin_router.post(
    "/sidebar-modules/update",
    response_model=AdminSidebarModulesResponse,
    dependencies=[Depends(get_admin_user_id)],
    summary="更新管理员侧边栏模块配置",
)
def update_admin_sidebar_modules(
    payload: SidebarModulesUpdateRequest, session: Annotated[Session, Depends(get_db)]
) -> dict[str, Any]:
    return SystemSettingsApplicationService(session, get_settings()).update_admin_sidebar_modules(payload.model_dump())
