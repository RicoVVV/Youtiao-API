from typing import Any

from pydantic import BaseModel


class ProviderTemplateSummaryResponse(BaseModel):
    template_id: str
    provider_type: str
    provider_id: str | None = None
    provider_name: str | None = None
    provider_logo_url: str | None = None
    label: str
    model_type: str
    summary: str
    tags: list[str]


class ProviderTemplateDetailResponse(ProviderTemplateSummaryResponse):
    input_schema: dict[str, Any]
    material_fields: dict[str, dict[str, Any]]
    derived_pricing_fields: list[dict[str, str]]
    default_pricing_rules: list[dict[str, Any]]
    example: dict[str, Any]
