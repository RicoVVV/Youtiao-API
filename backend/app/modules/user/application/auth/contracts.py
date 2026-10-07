"""用户认证应用层对 API 暴露的稳定数据契约。"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class AuthenticatedUser:
    """已通过会话校验的最小用户快照，不暴露 ORM 状态。"""

    id: UUID
    username: str
    is_active: bool
    is_admin: bool
    created_at: datetime


@dataclass(frozen=True, slots=True)
class UserProfileData:
    """当前用户资料查询用例返回的安全账号与运营数据投影。"""

    id: UUID
    username: str
    is_active: bool
    is_admin: bool
    created_at: datetime
    balance: str
    usage: str
