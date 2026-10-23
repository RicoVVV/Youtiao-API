"""用户侧监控可见范围配置 ORM 模型，单行保存管理员选择的分组与请求类型。

管理员开启限制后，用户侧监控只展示 ``group_ids`` 中的分组与 ``request_types`` 中的请求类型；
未开启限制时，用户可见其全部分组与 text/image/video 三种类型。
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, Column, DateTime, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field

from app.core.database import SQLModelBase

MONITOR_USER_VISIBILITY_ID = UUID(int=4)
"""用户侧监控可见范围配置固定使用的主键，保证配置表始终只有一行。"""


class MonitorUserVisibility(SQLModelBase, table=True):
    """保存用户侧监控的可见范围开关、分组白名单与请求类型白名单。"""

    __tablename__ = "monitor_user_visibility"

    id: UUID = Field(default=MONITOR_USER_VISIBILITY_ID, primary_key=True, description="配置主键，固定值")
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now(), comment="创建时间"),
    )
    updated_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(), comment="更新时间"
        ),
    )
    enabled: bool = Field(
        default=False,
        sa_column=Column(
            Boolean,
            nullable=False,
            server_default="false",
            comment="是否限制用户侧监控可见范围，false 表示用户可见全部分组与请求类型",
        ),
    )
    group_ids: list[int] = Field(
        default_factory=list,
        sa_column=Column(
            JSONB,
            nullable=False,
            server_default="'[]'::jsonb",
            comment="开启限制后允许用户看到的分组标识列表",
        ),
    )
    request_types: list[str] = Field(
        default_factory=list,
        sa_column=Column(
            JSONB,
            nullable=False,
            server_default="'[]'::jsonb",
            comment="开启限制后允许用户看到的请求类型列表",
        ),
    )
