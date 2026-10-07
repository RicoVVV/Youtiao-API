"""所有 ORM 实体复用的主键与创建时间字段定义。

本模块只提供持久化字段约定，不承载领域状态、更新语义或删除策略。
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, Uuid, func
from sqlmodel import Field


class UUIDPrimaryKeyMixin:
    """为业务实体提供应用侧生成的 UUID 主键。

    UUID 在 ORM 新建对象时生成，使异步任务和跨服务引用可在数据库提交前确定标识。
    """

    id: UUID = Field(
        default_factory=uuid4,
        sa_column=Column(Uuid, primary_key=True, nullable=False, comment="应用侧生成的业务主键"),
    )


class CreatedAtMixin:
    """为业务实体记录数据库服务器生成的 UTC 创建时间。

    创建时间只表达首次落库时刻；业务状态变更时间必须由领域模型单独保存。
    """

    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
            comment="数据库服务器生成的 UTC 创建时间",
        ),
    )
