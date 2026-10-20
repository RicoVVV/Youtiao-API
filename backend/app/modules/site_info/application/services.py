"""站点信息应用服务，承载维护用例与仪表板读取投影。"""

from typing import Any
from uuid import UUID

from sqlmodel import Session

from app.core.errors import NotFoundError
from app.modules.site_info.crud import SiteInfoCrud
from app.modules.site_info.model import SiteInfo


class SiteInfoApplicationService:
    """提供站点信息的分页查询、维护与启用项读取的事务用例。"""

    def __init__(self, session: Session) -> None:
        """绑定请求会话并初始化站点信息数据访问。"""

        self._session = session
        self._crud = SiteInfoCrud(session)

    def list_page(
        self,
        *,
        keyword: str | None,
        is_active: bool | None,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        """分页返回站点信息管理投影。"""

        total, items = self._crud.list_page(keyword=keyword, is_active=is_active, page=page, page_size=page_size)
        return {
            "items": [self._projection(item) for item in items],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def get_detail(self, site_info_id: UUID) -> dict[str, Any]:
        """返回单条站点信息管理投影。"""

        return self._projection(self._require(site_info_id))

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        """新增站点信息。"""

        site_info = SiteInfo(
            api_url=payload["api_url"],
            route_name=payload["route_name"],
            description=payload.get("description") or "",
            badge_color=payload.get("badge_color") or "blue",
            sort_order=payload.get("sort_order") or 0,
            is_active=payload.get("is_active", True),
        )
        try:
            self._crud.add(site_info)
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
        return self._projection(site_info)

    def update(self, payload: dict[str, Any]) -> dict[str, Any]:
        """按字段更新站点信息。"""

        site_info = self._require(payload["site_info_id"])
        for field in ("api_url", "route_name", "description", "badge_color", "sort_order", "is_active"):
            if field in payload and payload[field] is not None:
                setattr(site_info, field, payload[field])
        try:
            self._session.add(site_info)
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
        return self._projection(site_info)

    def update_status(self, *, site_info_id: UUID, is_active: bool) -> dict[str, Any]:
        """启用或停用站点信息。"""

        site_info = self._require(site_info_id)
        site_info.is_active = is_active
        try:
            self._session.add(site_info)
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
        return self._projection(site_info)

    def delete(self, site_info_id: UUID) -> None:
        """逻辑删除站点信息。"""

        site_info = self._require(site_info_id)
        try:
            self._crud.soft_delete(site_info)
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise

    def list_active_views(self) -> list[dict[str, Any]]:
        """返回仪表板展示所需的启用中站点信息投影。"""

        return [self._dashboard_projection(item) for item in self._crud.list_active()]

    def _require(self, site_info_id: UUID) -> SiteInfo:
        site_info = self._crud.get(site_info_id)
        if site_info is None:
            raise NotFoundError("站点信息不存在")
        return site_info

    @staticmethod
    def _projection(site_info: SiteInfo) -> dict[str, Any]:
        return {
            "id": site_info.id,
            "api_url": site_info.api_url,
            "route_name": site_info.route_name,
            "description": site_info.description,
            "badge_color": site_info.badge_color,
            "sort_order": site_info.sort_order,
            "is_active": site_info.is_active,
            "created_at": site_info.created_at,
            "updated_at": site_info.updated_at,
        }

    @staticmethod
    def _dashboard_projection(site_info: SiteInfo) -> dict[str, Any]:
        return {
            "id": site_info.id,
            "api_url": site_info.api_url,
            "route_name": site_info.route_name,
            "description": site_info.description,
            "badge_color": site_info.badge_color,
        }
