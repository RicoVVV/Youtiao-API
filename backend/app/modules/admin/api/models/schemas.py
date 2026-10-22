from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, Field


class ModelCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=512)
    """模型介绍；展示在模型广场卡片与详情，留空时广场回退展示模板简介。"""
    template_id: str | None = Field(default=None, min_length=1, max_length=128)
    """模型模板；留空时按模型名自动匹配内置价格目录。"""
    provider_id: str | None = Field(default=None, min_length=1, max_length=64)
    """模型 Provider；指定时只在该 Provider 的预设模型价格内匹配，未命中必须提供 pricing_rules。"""
    model_type: str | None = Field(default=None, min_length=1, max_length=32)
    """模型类型；留空时取模板声明的类型。"""
    input_contract: dict[str, Any] | None = None
    pricing_fields: list[str] | None = Field(default=None, max_length=64)
    """参与计价的输入字段；留空时按模板定价规则自动推导。"""
    pricing_rules: list[dict[str, Any]] | None = Field(default=None, max_length=20)
    """手动定价规则；未命中 Provider 预设价格时必填，形状与定价规则创建接口一致。"""
    token_group_ids: list[Annotated[int, Field(gt=0)]] | None = Field(default=None, max_length=50)
    """播种默认定价规则的目标令牌分组；留空或空数组表示系统默认分组。"""
    default_concurrency_limit: int | None = Field(default=None, ge=0, le=10000)
    active: bool = True


class ModelUpdateRequest(BaseModel):
    model_id: UUID
    name: str | None = Field(default=None, min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=512)
    model_type: str | None = Field(default=None, min_length=1, max_length=32)
    template_id: str | None = Field(default=None, min_length=1, max_length=128)
    input_contract: dict[str, Any] | None = None
    pricing_fields: list[str] | None = Field(default=None, max_length=64)
    default_concurrency_limit: int | None = Field(default=None, ge=0, le=10000)
    active: bool | None = None


class ModelStatusUpdateRequest(BaseModel):
    model_id: UUID
    active: bool


class ModelDeleteRequest(BaseModel):
    model_id: UUID


class ModelCopyRequest(BaseModel):
    model_id: UUID


class ModelProviderItem(BaseModel):
    """创建模型时可选的上游 Provider 及其支持的模型类型。"""

    provider_id: str
    provider_name: str | None = None
    provider_logo_url: str | None = None
    model_types: list[str]


class ModelProviderListResponse(BaseModel):
    items: list[ModelProviderItem]


class ModelBatchPreviewRequest(BaseModel):
    """批量预览所选上游模型的模板与预设定价。"""

    model_names: list[str] = Field(min_length=1, max_length=200)
    provider_id: str | None = Field(default=None, min_length=1, max_length=64)
    model_type: str | None = Field(default=None, min_length=1, max_length=32)


class ModelPricingSummaryItem(BaseModel):
    """单个计费项的价格摘要，供批量选择列表展示。"""

    kind: str | None = None
    label: str | None = None
    unit_amount: str | None = None
    currency: str | None = None


class ModelBatchPreviewItem(BaseModel):
    """批量预览中的单个模型结果；解析失败时仅返回错误信息。"""

    model_name: str
    matched: bool
    requires_pricing_input: bool
    match_type: str
    template_id: str | None = None
    model_type: str | None = None
    provider_id: str | None = None
    provider_name: str | None = None
    provider_logo_url: str | None = None
    pricing_summary: list[ModelPricingSummaryItem] = Field(default_factory=list)
    pricing_rules: list[dict[str, Any]] = Field(default_factory=list)
    pricing_modifiers: list[dict[str, Any]] = Field(default_factory=list)
    pricing_fields: list[str] = Field(default_factory=list)
    input_schema: dict[str, Any] | None = None
    error: str | None = None


class ModelBatchPreviewSummary(BaseModel):
    total: int
    preset_matched: int
    requires_pricing_input: int
    failed: int


class ModelBatchPreviewResponse(BaseModel):
    items: list[ModelBatchPreviewItem]
    summary: ModelBatchPreviewSummary


class ModelBatchCreateItemRequest(BaseModel):
    """批量创建中的单个模型；未提供的字段继承批量请求的公共配置。"""

    name: str = Field(min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=512)
    provider_id: str | None = Field(default=None, min_length=1, max_length=64)
    template_id: str | None = Field(default=None, min_length=1, max_length=128)
    model_type: str | None = Field(default=None, min_length=1, max_length=32)
    pricing_rules: list[dict[str, Any]] | None = Field(default=None, max_length=20)
    default_concurrency_limit: int | None = Field(default=None, ge=0, le=10000)
    active: bool = True


class ModelBatchCreateRequest(BaseModel):
    """批量创建模型；不接收令牌分组，默认定价播种到系统默认分组。"""

    provider_id: str | None = Field(default=None, min_length=1, max_length=64)
    items: list[ModelBatchCreateItemRequest] = Field(min_length=1, max_length=200)


class ModelBatchCreateItemResponse(BaseModel):
    id: str
    name: str
    pricing_configured: bool


class ModelBatchCreateResponse(BaseModel):
    items: list[ModelBatchCreateItemResponse]
