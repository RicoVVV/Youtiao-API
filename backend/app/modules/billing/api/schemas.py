"""用户兑换 HTTP 请求 DTO。"""

from pydantic import BaseModel, Field


class RedemptionRequest(BaseModel):
    """用户核销兑换码的请求参数。"""

    code: str = Field(min_length=8, max_length=256)
