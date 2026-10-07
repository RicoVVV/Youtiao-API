from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlmodel import Session

from app.core.auth import get_admin_user_id
from app.core.database import get_db
from app.modules.admin.api.models.schemas import (
    ModelCopyRequest,
    ModelCreateRequest,
    ModelDeleteRequest,
    ModelStatusUpdateRequest,
    ModelUpdateRequest,
)
from app.modules.admin.application.model_config.services import AdminModelConfigApplicationService

router = APIRouter(prefix="/models", tags=["管理员模型配置"])


@router.post(
    "/create", status_code=status.HTTP_201_CREATED, dependencies=[Depends(get_admin_user_id)], summary="创建模型"
)
def create_model(payload: ModelCreateRequest, session: Annotated[Session, Depends(get_db)]) -> dict[str, object]:
    return AdminModelConfigApplicationService(session).create_model(payload.model_dump())


@router.post("/update", dependencies=[Depends(get_admin_user_id)], summary="更新模型")
def update_model(payload: ModelUpdateRequest, session: Annotated[Session, Depends(get_db)]) -> dict[str, object]:
    return AdminModelConfigApplicationService(session).update_model(payload.model_dump(exclude_unset=True))


@router.post("/update-status", dependencies=[Depends(get_admin_user_id)], summary="更新模型状态")
def update_model_status(
    payload: ModelStatusUpdateRequest, session: Annotated[Session, Depends(get_db)]
) -> dict[str, object]:
    return AdminModelConfigApplicationService(session).update_model_status(payload.model_dump())


@router.post("/delete", dependencies=[Depends(get_admin_user_id)], summary="删除模型")
def delete_model(payload: ModelDeleteRequest, session: Annotated[Session, Depends(get_db)]) -> dict[str, bool]:
    AdminModelConfigApplicationService(session).delete_model(payload.model_dump())
    return {"success": True}


@router.post(
    "/copy", status_code=status.HTTP_201_CREATED, dependencies=[Depends(get_admin_user_id)], summary="复制模型"
)
def copy_model(payload: ModelCopyRequest, session: Annotated[Session, Depends(get_db)]) -> dict[str, object]:
    return AdminModelConfigApplicationService(session).copy_model(payload.model_dump())


@router.get("/list", dependencies=[Depends(get_admin_user_id)], summary="查询模型列表")
def list_models(
    session: Annotated[Session, Depends(get_db)],
    model_name: Annotated[str | None, Query(max_length=128)] = None,
    provider_id: Annotated[str | None, Query(max_length=64)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict[str, object]:
    total, items = AdminModelConfigApplicationService(session).list_models(
        model_name=model_name, provider_id=provider_id, page=page, page_size=page_size
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/detail", dependencies=[Depends(get_admin_user_id)], summary="查询模型详情")
def get_model(model_id: Annotated[UUID, Query()], session: Annotated[Session, Depends(get_db)]) -> dict[str, object]:
    return AdminModelConfigApplicationService(session).get_model(model_id)


@router.get("/match-preview", dependencies=[Depends(get_admin_user_id)], summary="预览模型名自动匹配结果")
def match_model_preview(
    session: Annotated[Session, Depends(get_db)],
    name: Annotated[str, Query(min_length=1, max_length=64)],
) -> dict[str, object]:
    return AdminModelConfigApplicationService(session).match_model_preview(name=name)
