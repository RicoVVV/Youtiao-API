"""钱包 HTTP 请求 DTO。"""

from decimal import Decimal

from pydantic import BaseModel, Field


class RechargeOrderRequest(BaseModel):
    """用户创建在线充值待支付订单的请求参数。"""

    amount: Decimal = Field(gt=0, decimal_places=6)
    payment_channel: str = Field(min_length=1, max_length=32)
