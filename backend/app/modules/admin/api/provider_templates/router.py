from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.bootstrap.container import get_provider_template_registry
from app.core.auth import get_admin_user_id
from app.modules.admin.api.provider_templates.schemas import (
    ProviderTemplateDetailResponse,
    ProviderTemplateSummaryResponse,
)
from app.modules.admin.application.provider_templates.services import AdminProviderTemplateApplicationService
from app.modules.providers.templates import ProviderTemplateRegistry

router = APIRouter(prefix="/provider-templates", tags=["管理员视频配置"])


@router.get("/list", dependencies=[Depends(get_admin_user_id)], summary="查询供应商模板列表")
def list_provider_templates(
    registry: Annotated[ProviderTemplateRegistry, Depends(get_provider_template_registry)],
) -> list[ProviderTemplateSummaryResponse]:
    return AdminProviderTemplateApplicationService(registry).list_templates()


@router.get("/detail", dependencies=[Depends(get_admin_user_id)], summary="查询供应商模板详情")
def get_provider_template(
    template_id: Annotated[str, Query(min_length=1, max_length=128)],
    registry: Annotated[ProviderTemplateRegistry, Depends(get_provider_template_registry)],
) -> ProviderTemplateDetailResponse:
    return AdminProviderTemplateApplicationService(registry).get_template(template_id)
