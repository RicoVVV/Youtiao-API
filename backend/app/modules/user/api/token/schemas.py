"""长期 Token HTTP 契约，定义签发、删除、启用、禁用和列表响应模型。"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class TokenRequest(BaseModel):
    """创建长期 Token 的可选展示标签。"""

    label: str | None = Field(default=None, max_length=128)
    group_ids: list[int] = Field(min_length=1, description="有序分组标识，首项为主分组，其余为按顺序回退的兜底分组")


class TokenDeletionRequest(BaseModel):
    """删除、启用或禁用长期 Token 时提交的目标凭证标识。"""

    token_id: UUID


class TokenGroupsUpdateRequest(TokenDeletionRequest):
    """整体替换 Token 分组绑定时提交的有序分组标识列表。"""

    group_ids: list[int] = Field(min_length=1, description="有序分组标识，首项为主分组，其余为按顺序回退的兜底分组")


class TokenGroupItem(BaseModel):
    """用户可选或 Token 已绑定的分组展示项。"""

    id: int
    name: str
    visibility: str
    is_active: bool
    description: str = ""
    price_multiplier: Decimal
    priority: int | None = None


class TokenListItem(BaseModel):
    """当前用户可查看的长期 Token 列表项。

    ``groups`` 为按绑定优先级升序的全部分组；``primary_group`` 为首个分组（主分组），
    ``fallback_groups`` 为其余按序兜底分组；未绑定任何分组时主分组为空且兜底分组为空列表。
    """

    id: UUID
    key_prefix: str
    label: str | None
    created_at: datetime
    last_used_at: datetime | None
    is_del: bool
    is_active: bool
    groups: list[TokenGroupItem]
    primary_group: TokenGroupItem | None = None
    fallback_groups: list[TokenGroupItem] = Field(default_factory=list)


class TokenListResponse(BaseModel):
    """当前用户查询长期 Token 时返回的分页结果。"""

    items: list[TokenListItem]
    total: int
    page: int
    page_size: int


class TokenCopyResponse(BaseModel):
    token_id: UUID
    token: str


class TokenViewResponse(BaseModel):
    id: UUID
    key_prefix: str
    label: str | None
    created_at: datetime
    last_used_at: datetime | None
    is_del: bool
    is_active: bool
    groups: list[TokenGroupItem]
    primary_group: TokenGroupItem | None = None
    fallback_groups: list[TokenGroupItem] = Field(default_factory=list)
