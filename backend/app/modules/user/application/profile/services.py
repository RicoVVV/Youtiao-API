"""用户资料应用服务，编排账号查询并返回安全的内部数据投影。"""

from decimal import Decimal
from uuid import UUID

from sqlmodel import Session

from app.core.errors import NotFoundError
from app.modules.user.application.auth.contracts import UserProfileData
from app.modules.user.crud.user_crud import UserCrud


class UserProfileApplicationService:
    """处理当前用户资料查询，不向 HTTP 层泄露 ORM 实体。"""

    def __init__(self, session: Session) -> None:
        """绑定由调用方管理的数据库会话，不提交或回滚事务。

        参数：session 为当前请求的数据库会话。
        返回值：无。
        异常/副作用：不执行事务边界控制。
        """

        self._users = UserCrud(session)

    def get_profile(self, user_id: UUID) -> UserProfileData:
        """查询用户资料并转换为不含密码与认证状态的安全投影。

        参数：user_id 为已通过鉴权的用户标识。
        返回值：用户不存在时返回 None，否则返回资料数据。
        异常/副作用：仅执行只读数据库查询。
        """

        statistics = self._users.get_profile_statistics(user_id)
        if statistics is None:
            raise NotFoundError("用户不存在")
        user, balance, usage = statistics
        return UserProfileData(
            id=user.id,
            username=user.username,
            is_active=user.is_active,
            is_admin=user.is_admin,
            created_at=user.created_at,
            balance=_format_amount(balance),
            usage=_format_amount(usage),
        )


def _format_amount(amount: Decimal) -> str:
    """将钱包十进制金额格式化为两位小数的账户展示值。"""

    return f"{amount:.2f}"
