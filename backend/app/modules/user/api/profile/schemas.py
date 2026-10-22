"""用户资料 HTTP 契约，定义余额预警设置的更新请求与响应。"""

from decimal import Decimal

from pydantic import BaseModel, Field


class BalanceAlertUpdateRequest(BaseModel):
    """用户自设的余额预警阈值与收件邮箱。

    ``threshold`` 传空表示关闭余额预警；``email`` 留空表示回退使用注册邮箱。
    """

    threshold: Decimal | None = Field(
        gt=0,
        max_digits=18,
        decimal_places=6,
        description="余额低于等于该值时发送提醒邮件（USD）；null 表示关闭余额预警",
    )
    email: str | None = Field(
        default=None,
        max_length=320,
        description="接收余额预警的邮箱；留空或 null 时使用注册邮箱",
    )


class BalanceAlertSettingsResponse(BaseModel):
    """用户余额预警设置；未设置时为 null。"""

    balance_alert_threshold: str | None
    balance_alert_email: str | None
