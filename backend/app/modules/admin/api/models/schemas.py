from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, Field


class ModelCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=512)
    """模型介绍；展示在模型广场卡片与详情，留空时广场回退展示模板简介。"""
    template_id: str | None = Field(default=None, min_length=1, max_length=128)
    """模型模板；留空时按模型名自动匹配内置价格目录。"""
    model_type: str | None = Field(default=None, min_length=1, max_length=32)
    """模型类型；留空时取模板声明的类型。"""
    input_contract: dict[str, Any] | None = None
    pricing_fields: list[str] | None = Field(default=None, max_length=64)
    """参与计价的输入字段；留空时按模板定价规则自动推导。"""
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
