"""用户概览接口 DTO。"""

from pydantic import BaseModel, ConfigDict, Field


class OverviewQuery(BaseModel):
    """描述用户概览接口的分页参数，用于控制公告消息返回条数。"""

    model_config = ConfigDict(extra="forbid")
    message_page: int = Field(default=1, ge=1)
    message_page_size: int = Field(default=10, ge=1, le=100)
