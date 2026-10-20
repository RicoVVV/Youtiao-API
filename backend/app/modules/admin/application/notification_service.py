"""管理员通知应用服务，承载通知维护、定向替换与全局唯一生效流转用例。"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlmodel import Session

from app.core.errors import NotFoundError, ValidationError
from app.modules.message.crud import NotificationCrud
from app.modules.message.model import Notification, NotificationTarget
from app.modules.user.crud.token_group_crud import TokenGroupCrud
from app.modules.user.crud.user_crud import UserCrud


class AdminNotificationApplicationService:
    """提供管理员维护通知与定向关系、保证全局唯一生效中的事务用例。"""

    def __init__(self, session: Session) -> None:
        """绑定请求会话并初始化通知数据访问。"""

        self._session = session
        self._crud = NotificationCrud(session)

    def list_page(self, *, keyword: str | None, is_active: bool | None, page: int, page_size: int) -> dict[str, Any]:
        """分页返回通知管理投影，附每条通知的定向明细。"""

        total, notifications = self._crud.list_page(
            keyword=keyword, is_active=is_active, page=page, page_size=page_size
        )
        targets_by_notification = self._group_targets(
            self._crud.list_targets_by_notification_ids([notification.id for notification in notifications])
        )
        return {
            "items": [
                self._projection(notification, targets_by_notification.get(notification.id, []))
                for notification in notifications
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def get_detail(self, notification_id: UUID) -> dict[str, Any]:
        """返回单条通知的管理投影与定向明细。"""

        notification = self._require(notification_id)
        return self._projection(notification, self._crud.list_targets(notification_id))

    def create(self, payload: dict[str, Any], *, created_by: UUID) -> dict[str, Any]:
        """创建通知并写入定向关系，校验可见范围与生效时间，并保证全局唯一生效中。"""

        user_ids, group_ids = self._resolve_targets(payload.get("targets"))
        is_public = bool(payload["is_public"])
        self._ensure_visibility(is_public, user_ids, group_ids)
        self._ensure_time_range(payload["start_at"], payload.get("expires_at"))
        notification = Notification(
            title=payload["title"],
            content=payload["content"],
            is_public=is_public,
            is_active=payload.get("is_active", True),
            start_at=payload["start_at"],
            expires_at=payload.get("expires_at"),
            created_by=created_by,
        )
        try:
            if notification.is_active:
                self._crud.deactivate_all_except(notification.id)
            self._crud.add(notification)
            self._crud.replace_targets(notification.id, user_ids=user_ids, group_ids=group_ids)
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
        return self._projection(notification, self._crud.list_targets(notification.id))

    def update(self, payload: dict[str, Any]) -> dict[str, Any]:
        """按字段更新通知；提交 targets 时整体替换定向关系，并在生效时保持全局唯一。"""

        notification = self._require(payload["notification_id"])
        if "title" in payload and payload["title"] is not None:
            notification.title = payload["title"]
        if "content" in payload and payload["content"] is not None:
            notification.content = payload["content"]
        if "is_public" in payload and payload["is_public"] is not None:
            notification.is_public = payload["is_public"]
        if "is_active" in payload and payload["is_active"] is not None:
            notification.is_active = payload["is_active"]
        if "start_at" in payload and payload["start_at"] is not None:
            notification.start_at = payload["start_at"]
        if "expires_at" in payload:
            notification.expires_at = payload["expires_at"]
        replace_targets = payload.get("targets") is not None
        if replace_targets:
            user_ids, group_ids = self._resolve_targets(payload["targets"])
        else:
            user_ids, group_ids = self._target_id_lists(self._crud.list_targets(notification.id))
        self._ensure_visibility(notification.is_public, user_ids, group_ids)
        self._ensure_time_range(notification.start_at, notification.expires_at)
        try:
            if notification.is_active:
                self._crud.deactivate_all_except(notification.id)
            self._session.add(notification)
            if replace_targets:
                self._crud.replace_targets(notification.id, user_ids=user_ids, group_ids=group_ids)
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
        return self._projection(notification, self._crud.list_targets(notification.id))

    def update_status(self, *, notification_id: UUID, is_active: bool) -> dict[str, Any]:
        """启用或下架通知；启用时自动下架其它通知。"""

        notification = self._require(notification_id)
        try:
            if is_active:
                self._crud.deactivate_all_except(notification.id)
            notification.is_active = is_active
            self._session.add(notification)
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
        return self._projection(notification, self._crud.list_targets(notification.id))

    def delete(self, notification_id: UUID) -> None:
        """逻辑删除通知及其定向关系。"""

        notification = self._require(notification_id)
        try:
            self._crud.soft_delete(notification)
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise

    def _require(self, notification_id: UUID) -> Notification:
        notification = self._crud.get(notification_id)
        if notification is None:
            raise NotFoundError("通知不存在")
        return notification

    def _resolve_targets(self, targets: dict[str, Any] | None) -> tuple[list[UUID], list[int]]:
        """去重并校验定向目标存在性，返回用户与分组标识列表。"""

        payload = targets or {}
        user_ids = list(dict.fromkeys(payload.get("user_ids") or []))
        group_ids = list(dict.fromkeys(payload.get("token_group_ids") or []))
        if user_ids and len(UserCrud(self._session).list_by_ids(user_ids)) != len(user_ids):
            raise ValidationError("定向用户不存在")
        if group_ids and len(TokenGroupCrud(self._session).list_groups_by_ids(set(group_ids))) != len(group_ids):
            raise ValidationError("定向分组不存在")
        return user_ids, group_ids

    @staticmethod
    def _ensure_visibility(is_public: bool, user_ids: list[UUID], group_ids: list[int]) -> None:
        """校验通知至少对全体用户或一个定向目标可见。"""

        if not is_public and not (user_ids or group_ids):
            raise ValidationError("通知必须对全体用户可见或至少有一个定向目标")

    @staticmethod
    def _ensure_time_range(start_at: datetime, expires_at: datetime | None) -> None:
        """校验过期时间必须晚于生效时间。"""

        if expires_at is not None and expires_at <= start_at:
            raise ValidationError("通知过期时间必须晚于生效时间")

    @staticmethod
    def _group_targets(targets: list[NotificationTarget]) -> dict[UUID, list[NotificationTarget]]:
        grouped: dict[UUID, list[NotificationTarget]] = {}
        for target in targets:
            grouped.setdefault(target.notification_id, []).append(target)
        return grouped

    @staticmethod
    def _target_id_lists(targets: list[NotificationTarget]) -> tuple[list[UUID], list[int]]:
        user_ids = [target.user_id for target in targets if target.user_id is not None]
        group_ids = [target.token_group_id for target in targets if target.token_group_id is not None]
        return user_ids, group_ids

    @classmethod
    def _projection(cls, notification: Notification, targets: list[NotificationTarget]) -> dict[str, Any]:
        user_ids, group_ids = cls._target_id_lists(targets)
        return {
            "id": notification.id,
            "title": notification.title,
            "content": notification.content,
            "is_public": notification.is_public,
            "is_active": notification.is_active,
            "start_at": notification.start_at,
            "expires_at": notification.expires_at,
            "created_at": notification.created_at,
            "updated_at": notification.updated_at,
            "targets": {
                "user_ids": user_ids,
                "token_group_ids": group_ids,
            },
        }
