"""用户端会员 RPC HTTP API。"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.core.auth import get_user_id
from app.core.database import get_db
from app.modules.membership.api.schemas import MembershipPublicPlanListResponse
from app.modules.membership.application.services import MembershipQueryService

router = APIRouter(tags=["会员"])


@router.get(
    "/membership-plans/list",
    response_model=MembershipPublicPlanListResponse,
    dependencies=[Depends(get_user_id)],
    summary="查询会员套餐列表",
)
def list_membership_plans(session: Annotated[Session, Depends(get_db)]) -> dict:
    return {"items": MembershipQueryService(session).list_public_plans()}
