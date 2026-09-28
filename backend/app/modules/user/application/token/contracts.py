"""长期 Token 应用层对外暴露的安全数据契约。"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from uuid import UUID


@dataclass(frozen=True, slots=True)
class TokenData:
    """归属用户可查看和复制的长期 Token 安全投影。

    ``groups`` 按绑定优先级升序排列，首个元素即主分组，其余元素为按序兜底分组。
    """

    id: UUID
    user_id: UUID
    token: str
    label: str | None
    created_at: datetime
    last_used_at: datetime | None
    is_del: bool
    is_active: bool
    groups: list["TokenGroupData"] = field(default_factory=list)

    @property
    def key_prefix(self) -> str:
        """返回用于界面展示和人工定位的 Token 固定前缀。"""

        return self.token[:11]

    @property
    def primary_group(self) -> "TokenGroupData | None":
        """返回首个绑定分组作为主分组，未绑定任何分组时为空。"""

        return self.groups[0] if self.groups else None

    @property
    def fallback_groups(self) -> list["TokenGroupData"]:
        """按绑定优先级返回除主分组外的全部兜底分组。"""

        return list(self.groups[1:])


@dataclass(frozen=True, slots=True)
class TokenPage:
    """长期 Token 分页查询的应用层结果。"""

    tokens: list[TokenData]
    total: int


@dataclass(frozen=True, slots=True)
class TokenGroupData:
    """供用户或管理员展示的 Token 分组安全投影。"""

    id: int
    name: str
    visibility: str
    is_active: bool
    description: str = ""
    price_multiplier: Decimal = Decimal("1.000000")
    priority: int | None = None


@dataclass(frozen=True, slots=True)
class RuntimeTokenGroups:
    """长期 Token 运行时解析出的全部有效分组上下文。"""

    token_id: UUID
    user_id: UUID
    groups: list[TokenGroupData]
