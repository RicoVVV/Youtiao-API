"""站点信息表的查询、持久化与逻辑删除。"""

from uuid import UUID

from sqlalchemy import ColumnElement, func, or_, select
from sqlmodel import Session

from app.modules.site_info.model import SiteInfo


class SiteInfoCrud:
    """封装站点信息的分页查询、单条读取与逻辑删除，不提交事务。"""

    def __init__(self, session: Session) -> None:
        """绑定调用方提供的事务会话。"""

        self._session = session

    def list_page(
        self,
        *,
        keyword: str | None,
        is_active: bool | None,
        page: int,
        page_size: int,
    ) -> tuple[int, list[SiteInfo]]:
        """按筛选条件分页读取站点信息，按展示排序升序。"""

        conditions: list[ColumnElement[bool]] = []
        if keyword:
            conditions.append(or_(SiteInfo.api_url.ilike(f"%{keyword}%"), SiteInfo.route_name.ilike(f"%{keyword}%")))
        if is_active is not None:
            conditions.append(SiteInfo.is_active.is_(is_active))
        total = self._session.scalar(select(func.count()).select_from(SiteInfo).where(*conditions)) or 0
        items = list(
            self._session.scalars(
                select(SiteInfo)
                .where(*conditions)
                .order_by(SiteInfo.sort_order, SiteInfo.created_at.desc(), SiteInfo.id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        return total, items

    def list_active(self) -> list[SiteInfo]:
        """读取全部启用中的站点信息，按展示排序升序。"""

        return list(
            self._session.scalars(
                select(SiteInfo)
                .where(SiteInfo.is_active.is_(True))
                .order_by(SiteInfo.sort_order, SiteInfo.created_at.desc(), SiteInfo.id)
            )
        )

    def get(self, site_info_id: UUID, *, include_deleted: bool = False) -> SiteInfo | None:
        """读取指定站点信息，可选包含已逻辑删除记录。"""

        return self._session.scalar(
            select(SiteInfo).where(SiteInfo.id == site_info_id).execution_options(include_deleted=include_deleted)
        )

    def add(self, site_info: SiteInfo) -> SiteInfo:
        """新增站点信息并刷新主键。"""

        self._session.add(site_info)
        self._session.flush()
        return site_info

    def soft_delete(self, site_info: SiteInfo) -> None:
        """逻辑删除站点信息，保留历史行。"""

        site_info.is_del = True
        self._session.add(site_info)
