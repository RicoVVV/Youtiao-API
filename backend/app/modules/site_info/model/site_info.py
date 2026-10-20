"""站点信息（API 快捷方式）的 ORM 映射。

本模块只保存站点信息条目自身；可见性、排序与维护规则由应用服务负责。
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, func
from sqlmodel import Field

from app.core.database import SQLModelBase


def _created_at_column(comment: str) -> Column:
    return Column(DateTime(timezone=True), nullable=False, server_default=func.now(), comment=comment)


def _updated_at_column(comment: str) -> Column:
    return Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(), comment=comment
    )


class SiteInfo(SQLModelBase, table=True):
    """仪表板展示的站点信息条目，承载 API 地址、路由描述与徽章颜色。"""

    __tablename__ = "site_info"

    id: UUID = Field(default_factory=uuid4, primary_key=True, description="站点信息主键")
    created_at: datetime | None = Field(default=None, sa_column=_created_at_column("站点信息创建时间"))
    updated_at: datetime | None = Field(default=None, sa_column=_updated_at_column("站点信息最近更新时间"))
    api_url: str = Field(sa_column=Column(String(2048), nullable=False, comment="API 地址"))
    route_name: str = Field(sa_column=Column(String(255), nullable=False, comment="路由描述"))
    description: str = Field(
        default="", sa_column=Column(Text(), nullable=False, server_default="", comment="说明信息")
    )
    badge_color: str = Field(
        default="blue",
        sa_column=Column(String(32), nullable=False, server_default="blue", comment="徽章颜色名称"),
    )
    sort_order: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False, server_default="0", comment="仪表板展示排序，越小越靠前"),
    )
    is_active: bool = Field(
        default=True,
        sa_column=Column(Boolean, nullable=False, server_default="true", comment="false 表示不在仪表板展示"),
    )
