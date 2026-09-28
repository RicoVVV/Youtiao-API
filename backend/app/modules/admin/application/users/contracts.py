"""管理员用户管理应用层的内部数据契约，不依赖 HTTP DTO。"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class AdminUserListItemData:
    """管理员用户列表的内部安全投影。"""

    id: UUID
    username: str
    is_active: bool
    is_admin: bool
    created_at: datetime
    balance: str
    usage: str
    active_lease_count: int


@dataclass(frozen=True, slots=True)
class AdminUserPage:
    """管理员用户分页查询的内部结果。"""

    users: list[AdminUserListItemData]
    total: int
