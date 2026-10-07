"""支付 options 键值模型，保存管理员维护的系统级支付配置。"""

from app.core.database import SQLModelBase
from sqlmodel import Field


class PaymentOption(SQLModelBase, table=True):
    """支付宝配置键值表；敏感值只能保存 Fernet 密文。"""

    __tablename__ = "options"
    key: str = Field(primary_key=True, max_length=128, description="配置键")
    value: str = Field(description="配置值或加密密文")
