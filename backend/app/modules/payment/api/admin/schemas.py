"""管理员支付流水 HTTP 请求与响应 DTO。"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class AdminPaymentOrderQuery(BaseModel):
    """管理员筛选已支付充值订单的公共条件，列表与导出共用。"""

    start_at: datetime = Field(description="支付时间下界（含），ISO8601")
    end_at: datetime = Field(description="支付时间上界（含），ISO8601")
    username: str | None = Field(default=None, min_length=1, max_length=128, description="按用户名精确匹配")
    payment_channel: str | None = Field(default=None, min_length=1, max_length=32, description="按支付渠道精确匹配")
    order_no: str | None = Field(default=None, min_length=1, max_length=64, description="按业务订单号精确匹配")


class AdminPaymentOrderListQuery(AdminPaymentOrderQuery):
    """管理员分页查询支付流水的请求参数。"""

    page: int = Field(default=1, ge=1, description="从 1 开始的页码")
    page_size: int = Field(default=20, ge=1, le=100, description="单页最大返回 100 条")


class AdminPaymentOrderExportQuery(AdminPaymentOrderQuery):
    """管理员导出支付流水的请求参数，与列表共用筛选条件但不分页。"""


class AdminPaymentOrderItem(BaseModel):
    """管理端支付流水单条展示数据。"""

    order_no: str = Field(description="本地业务订单号")
    user_id: UUID = Field(description="充值用户标识")
    username: str = Field(description="充值用户名")
    topup_amount: str = Field(description="充值到账人民币金额")
    pay_amount: str = Field(description="实际支付金额")
    payment_channel: str = Field(description="支付渠道标识")
    payment_method: str = Field(description="渠道内支付方式")
    channel_transaction_id: str | None = Field(default=None, description="支付渠道交易号")
    status: str = Field(description="订单状态")
    created_at: datetime | None = Field(default=None, description="订单创建时间")
    paid_at: datetime | None = Field(default=None, description="支付成功时间")


class AdminPaymentOrderListResponse(BaseModel):
    """管理端分页查询支付流水的响应数据。"""

    items: list[AdminPaymentOrderItem] = Field(description="当前页支付流水")
    total: int = Field(description="筛选条件下支付流水总数")
    page: int = Field(description="当前页码")
    page_size: int = Field(description="当前页条数")
