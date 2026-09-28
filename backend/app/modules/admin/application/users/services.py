"""提供管理员用户查询应用服务及独立于 HTTP DTO 的运营数据投影。"""

from decimal import Decimal

from sqlmodel import Session

from app.core.errors import NotFoundError
from app.modules.admin.application.users.contracts import AdminUserListItemData, AdminUserPage
from app.modules.admin.crud.user_crud import AdminUserCrud


class AdminUserApplicationService:
    """处理管理员用户查询用例。"""

    def __init__(self, session: Session) -> None:
        """接收调用方管理的数据库会话；服务自身不提交事务。"""

        self._session = session
        self._users = AdminUserCrud(session)

    def list_users(self, *, page: int, page_size: int) -> AdminUserPage:
        """按创建时间倒序读取用户列表及运营统计。

        page 从 1 开始，page_size 为单页数量；返回当前页安全投影和未分页总数。
        只读数据库。
        """

        total, rows = self._users.list_user_statistics(page=page, page_size=page_size)
        users = [
            AdminUserListItemData(
                id=user.id,
                username=user.username,
                is_active=user.is_active,
                is_admin=user.is_admin,
                created_at=user.created_at,
                balance=_format_amount(balance or Decimal("0")),
                usage=_format_amount(usage or Decimal("0")),
                active_lease_count=int(active_lease_count or 0),
            )
            for user, balance, usage, active_lease_count in rows
        ]
        return AdminUserPage(users=users, total=total)

    def get_user_by_username(self, *, username: str) -> AdminUserListItemData:
        """按用户名精确读取单个用户的安全运营投影。

        参数：username 为待精确匹配的用户名。
        返回值：用户的安全身份与运营数据。
        异常：用户不存在时抛出 ValueError。
        """

        row = self._users.get_user_statistics_by_username(username=username)
        if row is None:
            raise NotFoundError("用户不存在")
        user, balance, usage, active_lease_count = row
        return AdminUserListItemData(
            id=user.id,
            username=user.username,
            is_active=user.is_active,
            is_admin=user.is_admin,
            created_at=user.created_at,
            balance=_format_amount(balance or Decimal("0")),
            usage=_format_amount(usage or Decimal("0")),
            active_lease_count=int(active_lease_count or 0),
        )


def _format_amount(amount: Decimal) -> str:
    """将钱包十进制金额格式化为两位小数的管理端展示值。"""

    return f"{amount:.2f}"
