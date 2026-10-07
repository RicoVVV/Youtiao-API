"""用户侧分组监控接口 DTO。"""

from pydantic import BaseModel, ConfigDict, Field


class GroupMonitorListQuery(BaseModel):
    """查询可用分组监控指标时的筛选条件。"""

    model_config = ConfigDict(extra="forbid")

    group_id: int | None = Field(default=None, description="可选，仅返回指定分组的指标")


class GroupMonitorTrendQuery(BaseModel):
    """查询单个分组监控趋势时的筛选条件。"""

    model_config = ConfigDict(extra="forbid")

    group_id: int = Field(description="待查询的 Token 分组标识")
    request_type: str | None = Field(default=None, pattern="^(text|image|video)$", description="可选，请求类型")
    hours: int = Field(default=24, ge=1, le=24, description="统计时长，最大 24 小时")
