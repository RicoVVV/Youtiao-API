from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlmodel import Session

from app.core.auth import get_admin_user_id
from app.core.database import get_db
from app.modules.admin.api.pricing_modifiers.schemas import (
    PricingModifierCopyRequest,
    PricingModifierCreateRequest,
    PricingModifierDeleteRequest,
    PricingModifierUpdateRequest,
)
from app.modules.admin.application.model_config.services import AdminModelConfigApplicationService

router = APIRouter(prefix="/pricing-modifiers", tags=["管理员计费配置"])


@router.post(
    "/create", status_code=status.HTTP_201_CREATED, dependencies=[Depends(get_admin_user_id)], summary="创建计费修正项"
)
def create_pricing_modifier(
    payload: PricingModifierCreateRequest, session: Annotated[Session, Depends(get_db)]
) -> dict[str, object]:
    return AdminModelConfigApplicationService(session).create_pricing_modifier(payload.model_dump())


@router.post("/update", dependencies=[Depends(get_admin_user_id)], summary="更新计费修正项")
def update_pricing_modifier(
    payload: PricingModifierUpdateRequest, session: Annotated[Session, Depends(get_db)]
) -> dict[str, object]:
    return AdminModelConfigApplicationService(session).update_pricing_modifier(payload.model_dump())


@router.post("/delete", dependencies=[Depends(get_admin_user_id)], summary="删除计费修正项")
def delete_pricing_modifier(
    payload: PricingModifierDeleteRequest, session: Annotated[Session, Depends(get_db)]
) -> dict[str, bool]:
    AdminModelConfigApplicationService(session).delete_pricing_modifier(payload.model_dump())
    return {"success": True}


@router.post(
    "/copy", status_code=status.HTTP_201_CREATED, dependencies=[Depends(get_admin_user_id)], summary="复制计费修正项"
)
def copy_pricing_modifier(
    payload: PricingModifierCopyRequest, session: Annotated[Session, Depends(get_db)]
) -> dict[str, object]:
    return AdminModelConfigApplicationService(session).copy_pricing_modifier(payload.model_dump())


@router.get("/list", dependencies=[Depends(get_admin_user_id)], summary="查询计费修正项列表")
def list_pricing_modifiers(
    session: Annotated[Session, Depends(get_db)],
    pricing_rule_id: Annotated[UUID | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict[str, object]:
    total, items = AdminModelConfigApplicationService(session).list_pricing_modifiers(
        pricing_rule_id=pricing_rule_id,
        page=page,
        page_size=page_size,
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/detail", dependencies=[Depends(get_admin_user_id)], summary="查询计费修正项详情")
def get_pricing_modifier(
    pricing_modifier_id: Annotated[UUID, Query()], session: Annotated[Session, Depends(get_db)]
) -> dict[str, object]:
    return AdminModelConfigApplicationService(session).get_pricing_modifier(pricing_modifier_id)
