"""管理端会员 RPC HTTP API。"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.core.auth import get_admin_user_id
from app.core.database import get_db
from app.modules.membership.api.schemas import (
    AdminMembershipLevelCreateRequest,
    AdminMembershipLevelDeleteRequest,
    AdminMembershipLevelListResponse,
    AdminMembershipLevelResponse,
    AdminMembershipLevelStatusRequest,
    AdminMembershipLevelUpdateRequest,
    AdminMembershipPlanCreateRequest,
    AdminMembershipPlanDeleteRequest,
    AdminMembershipPlanResponse,
    AdminMembershipPlanStatusRequest,
    AdminMembershipPlanUpdateRequest,
    AdminMembershipRecordListResponse,
    AdminUserMembershipGrantRequest,
    AdminUserMembershipListResponse,
    AdminUserMembershipResponse,
    AdminUserMembershipRevokeRequest,
)
from app.modules.membership.application.admin_services import AdminMembershipApplicationService

router = APIRouter(prefix="/admin", tags=["管理员会员"])


@router.get(
    "/membership-levels/list",
    response_model=AdminMembershipLevelListResponse,
    dependencies=[Depends(get_admin_user_id)],
    summary="查询会员等级列表",
)
def list_membership_levels(
    session: Annotated[Session, Depends(get_db)],
    is_public: Annotated[bool | None, Query()] = None,
    is_active: Annotated[bool | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict:
    total, items = AdminMembershipApplicationService(session).list_levels(is_public, is_active, page, page_size)
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get(
    "/membership-levels/detail",
    response_model=AdminMembershipLevelResponse,
    dependencies=[Depends(get_admin_user_id)],
    summary="查询会员等级详情",
)
def get_membership_level(level_id: Annotated[UUID, Query()], session: Annotated[Session, Depends(get_db)]) -> dict:
    return AdminMembershipApplicationService(session).get_level_detail(level_id)


@router.post(
    "/membership-levels/create",
    response_model=AdminMembershipLevelResponse,
    dependencies=[Depends(get_admin_user_id)],
    summary="创建会员等级",
)
def create_membership_level(
    payload: AdminMembershipLevelCreateRequest, session: Annotated[Session, Depends(get_db)]
) -> dict:
    return AdminMembershipApplicationService(session).create_level(**payload.model_dump())


@router.post(
    "/membership-levels/update",
    response_model=AdminMembershipLevelResponse,
    dependencies=[Depends(get_admin_user_id)],
    summary="更新会员等级",
)
def update_membership_level(
    payload: AdminMembershipLevelUpdateRequest, session: Annotated[Session, Depends(get_db)]
) -> dict:
    return AdminMembershipApplicationService(session).update_level(**payload.model_dump())


@router.post(
    "/membership-levels/update-status",
    response_model=AdminMembershipLevelResponse,
    dependencies=[Depends(get_admin_user_id)],
    summary="更新会员等级状态",
)
def update_membership_level_status(
    payload: AdminMembershipLevelStatusRequest, session: Annotated[Session, Depends(get_db)]
) -> dict:
    return AdminMembershipApplicationService(session).update_level_status(**payload.model_dump())


@router.post("/membership-levels/delete", dependencies=[Depends(get_admin_user_id)], summary="删除会员等级")
def delete_membership_level(
    payload: AdminMembershipLevelDeleteRequest, session: Annotated[Session, Depends(get_db)]
) -> dict:
    AdminMembershipApplicationService(session).delete_level(**payload.model_dump())
    return {"success": True}


@router.post(
    "/membership-plans/create",
    response_model=AdminMembershipPlanResponse,
    dependencies=[Depends(get_admin_user_id)],
    summary="创建会员套餐",
)
def create_membership_plan(
    payload: AdminMembershipPlanCreateRequest, session: Annotated[Session, Depends(get_db)]
) -> dict:
    return AdminMembershipApplicationService(session).create_plan(**payload.model_dump())


@router.post(
    "/membership-plans/update",
    response_model=AdminMembershipPlanResponse,
    dependencies=[Depends(get_admin_user_id)],
    summary="更新会员套餐",
)
def update_membership_plan(
    payload: AdminMembershipPlanUpdateRequest, session: Annotated[Session, Depends(get_db)]
) -> dict:
    return AdminMembershipApplicationService(session).update_plan(**payload.model_dump())


@router.post(
    "/membership-plans/update-status",
    response_model=AdminMembershipPlanResponse,
    dependencies=[Depends(get_admin_user_id)],
    summary="更新会员套餐状态",
)
def update_membership_plan_status(
    payload: AdminMembershipPlanStatusRequest, session: Annotated[Session, Depends(get_db)]
) -> dict:
    return AdminMembershipApplicationService(session).update_plan_status(**payload.model_dump())


@router.post("/membership-plans/delete", dependencies=[Depends(get_admin_user_id)], summary="删除会员套餐")
def delete_membership_plan(
    payload: AdminMembershipPlanDeleteRequest, session: Annotated[Session, Depends(get_db)]
) -> dict:
    AdminMembershipApplicationService(session).delete_plan(**payload.model_dump())
    return {"success": True}


@router.get(
    "/user-memberships/list",
    response_model=AdminUserMembershipListResponse,
    dependencies=[Depends(get_admin_user_id)],
    summary="查询用户会员列表",
)
def list_user_memberships(
    session: Annotated[Session, Depends(get_db)],
    user_id: Annotated[UUID | None, Query()] = None,
    level_id: Annotated[UUID | None, Query()] = None,
    is_active: Annotated[bool | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict:
    total, items = AdminMembershipApplicationService(session).list_user_memberships(
        user_id, level_id, is_active, page, page_size
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get(
    "/user-memberships/records/list",
    response_model=AdminMembershipRecordListResponse,
    dependencies=[Depends(get_admin_user_id)],
    summary="查询会员流水列表",
)
def list_membership_records(
    session: Annotated[Session, Depends(get_db)],
    user_id: Annotated[UUID | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict:
    total, items = AdminMembershipApplicationService(session).list_records(user_id, page, page_size)
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.post("/user-memberships/grant", response_model=AdminUserMembershipResponse, summary="授予用户会员")
def grant_user_membership(
    payload: AdminUserMembershipGrantRequest,
    operator_id: Annotated[UUID, Depends(get_admin_user_id)],
    session: Annotated[Session, Depends(get_db)],
) -> dict:
    return AdminMembershipApplicationService(session).grant(**payload.model_dump(), operator_id=operator_id)


@router.post("/user-memberships/revoke", response_model=AdminUserMembershipResponse, summary="撤销用户会员")
def revoke_user_membership(
    payload: AdminUserMembershipRevokeRequest,
    operator_id: Annotated[UUID, Depends(get_admin_user_id)],
    session: Annotated[Session, Depends(get_db)],
) -> dict:
    return AdminMembershipApplicationService(session).revoke(**payload.model_dump(), operator_id=operator_id)
