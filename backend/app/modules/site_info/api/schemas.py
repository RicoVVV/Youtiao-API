"""管理员站点信息 RPC API 的请求与响应契约。

本模块仅定义站点信息管理端接口的数据校验规则，不包含鉴权、事务或业务编排。
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class AdminSiteInfoCreateRequest(BaseModel):
    """描述创建站点信息时提交的 API 地址、路由描述与展示配置。"""

    api_url: str = Field(min_length=1, max_length=2048)
    route_name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=2000)
    badge_color: str = Field(default="blue", min_length=1, max_length=32)
    sort_order: int = Field(default=0, ge=0)
    is_active: bool = True


class AdminSiteInfoUpdateRequest(BaseModel):
    """描述按字段更新站点信息时提交的目标标识与可变字段。"""

    site_info_id: UUID
    api_url: str | None = Field(default=None, min_length=1, max_length=2048)
    route_name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    badge_color: str | None = Field(default=None, min_length=1, max_length=32)
    sort_order: int | None = Field(default=None, ge=0)
    is_active: bool | None = None


class AdminSiteInfoStatusRequest(BaseModel):
    """描述启用或停用站点信息时提交的目标标识与目标状态。"""

    site_info_id: UUID
    is_active: bool


class AdminSiteInfoDeleteRequest(BaseModel):
    """描述逻辑删除站点信息时提交的目标标识。"""

    site_info_id: UUID


class AdminSiteInfoResponse(BaseModel):
    """描述管理员查询或维护站点信息时返回的完整管理投影。"""

    id: UUID
    api_url: str
    route_name: str
    description: str
    badge_color: str
    sort_order: int
    is_active: bool
    created_at: datetime | None
    updated_at: datetime | None


class AdminSiteInfoListResponse(BaseModel):
    """描述管理员分页查询站点信息时返回的分页结果。"""

    items: list[AdminSiteInfoResponse]
    total: int
    page: int
    page_size: int
