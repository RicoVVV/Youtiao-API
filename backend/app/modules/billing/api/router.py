"""用户兑换核销 HTTP 接口。"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.core.auth import get_user_id
from app.core.database import get_db
from app.modules.billing.api.schemas import RedemptionRequest
from app.modules.billing.application.services import BillingApplicationService

router = APIRouter()


@router.post("/billing/redemptions/redeem", summary="核销兑换码", tags=["用户账务"])
def redeem(
    payload: RedemptionRequest,
    user_id: Annotated[UUID, Depends(get_user_id)],
    session: Annotated[Session, Depends(get_db)],
) -> dict:
    return BillingApplicationService(session).redeem(user_id=user_id, raw_code=payload.code)
