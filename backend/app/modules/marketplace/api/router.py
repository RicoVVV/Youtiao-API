from typing import Annotated

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.core.database import get_db
from app.modules.marketplace.api.schemas import ModelMarketplaceDetailQuery, ModelMarketplaceListQuery
from app.modules.marketplace.application.services import ModelMarketplaceApplicationService

router = APIRouter(prefix="/model-marketplace", tags=["模型广场"])


@router.get("/list", summary="查询模型广场")
def list_models(
    payload: Annotated[ModelMarketplaceListQuery, Depends()], session: Annotated[Session, Depends(get_db)]
) -> dict[str, object]:
    total, items = ModelMarketplaceApplicationService(session).list_models(**payload.model_dump())
    return {"items": items, "total": total, "page": payload.page, "page_size": payload.page_size}


@router.get("/detail", summary="查询模型广场详情")
def get_model(
    payload: Annotated[ModelMarketplaceDetailQuery, Depends()], session: Annotated[Session, Depends(get_db)]
) -> dict[str, object]:
    return ModelMarketplaceApplicationService(session).get_model(payload.model_id)
