"""支付配置数据访问层，封装 options 键值的读取和更新。"""

from app.modules.payment.model import PaymentOption
from sqlmodel import Session, select


class PaymentSettingsCrud:
    """提供支付配置的持久化操作，不包含配置业务规则。"""

    def __init__(self, session: Session) -> None:
        """绑定当前请求的数据库会话。"""

        self._session = session

    def get_values(self) -> dict[str, str]:
        """读取全部支付配置键值。"""

        return {item.key: item.value for item in self._session.exec(select(PaymentOption)).all()}

    def upsert_values(self, values: dict[str, str]) -> None:
        """新增或更新支付配置键值，不提交事务。"""

        for key, value in values.items():
            item = self._session.get(PaymentOption, key) or PaymentOption(key=key, value=value)
            item.value = value
            self._session.add(item)
