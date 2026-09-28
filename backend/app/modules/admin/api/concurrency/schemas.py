"""管理员用户模型并发管理 HTTP 请求与响应契约。"""

from uuid import UUID

from pydantic import BaseModel, Field


class AdminUserModelConcurrencyOverrideRequest(BaseModel):
    """创建或覆盖用户指定模型并发上限的输入模型。"""

    user_id: UUID
    model_id: UUID
    concurrency_limit: int = Field(ge=0, le=10000)
    active: bool = True


class AdminUserModelConcurrencyOverrideResponse(BaseModel):
    """用户模型并发上限覆盖的安全管理投影。"""

    id: UUID
    user_id: UUID
    model_id: UUID
    concurrency_limit: int
    active: bool

    model_config = {"from_attributes": True}


class AdminUserModelConcurrencyUsageResponse(BaseModel):
    """用户在指定模型下的并发覆盖和活跃租约统计。"""

    user_id: UUID
    items: list[AdminUserModelConcurrencyOverrideResponse]
    active_lease_counts: dict[UUID, int]
