"""管理员消息应用服务，承载消息维护、定向替换与状态流转用例。"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlmodel import Session

from app.core.errors import NotFoundError, ValidationError
from app.modules.message.crud import MessageCrud
from app.modules.message.model import Message, MessageTarget, MessageType
from app.modules.user.crud.token_group_crud import TokenGroupCrud
from app.modules.user.crud.user_crud import UserCrud


class AdminMessageApplicationService:
    """提供管理员维护消息与定向关系的事务用例。"""

    def __init__(self, session: Session) -> None:
        """绑定请求会话并初始化消息数据访问。"""

        self._session = session
        self._crud = MessageCrud(session)

    def list_page(
        self,
        *,
        keyword: str | None,
        message_type: MessageType | None,
        is_active: bool | None,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        """分页返回消息管理投影，附每条消息的定向明细。"""

        total, messages = self._crud.list_page(
            keyword=keyword, message_type=message_type, is_active=is_active, page=page, page_size=page_size
        )
        targets_by_message = self._group_targets(
            self._crud.list_targets_by_message_ids([message.id for message in messages])
        )
        return {
            "items": [self._projection(message, targets_by_message.get(message.id, [])) for message in messages],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def get_detail(self, message_id: UUID) -> dict[str, Any]:
        """返回单条消息的管理投影与定向明细。"""

        message = self._require(message_id)
        return self._projection(message, self._crud.list_targets(message_id))

    def create(self, payload: dict[str, Any], *, created_by: UUID) -> dict[str, Any]:
        """创建消息并写入定向关系，校验可见范围与生效时间。"""

        user_ids, group_ids = self._resolve_targets(payload.get("targets"))
        is_public = bool(payload["is_public"])
        self._ensure_visibility(is_public, user_ids, group_ids)
        self._ensure_time_range(payload["start_at"], payload.get("expires_at"))
        message = Message(
            title=payload["title"],
            content=payload["content"],
            type=payload["type"],
            is_public=is_public,
            is_active=payload.get("is_active", True),
            start_at=payload["start_at"],
            expires_at=payload.get("expires_at"),
            created_by=created_by,
        )
        try:
            self._crud.add(message)
            self._crud.replace_targets(message.id, user_ids=user_ids, group_ids=group_ids)
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
        return self._projection(message, self._crud.list_targets(message.id))

    def update(self, payload: dict[str, Any]) -> dict[str, Any]:
        """按字段更新消息；提交 targets 时整体替换定向关系。"""

        message = self._require(payload["message_id"])
        if "title" in payload and payload["title"] is not None:
            message.title = payload["title"]
        if "content" in payload and payload["content"] is not None:
            message.content = payload["content"]
        if "type" in payload and payload["type"] is not None:
            message.type = payload["type"]
        if "is_public" in payload and payload["is_public"] is not None:
            message.is_public = payload["is_public"]
        if "is_active" in payload and payload["is_active"] is not None:
            message.is_active = payload["is_active"]
        if "start_at" in payload and payload["start_at"] is not None:
            message.start_at = payload["start_at"]
        if "expires_at" in payload:
            message.expires_at = payload["expires_at"]
        replace_targets = payload.get("targets") is not None
        if replace_targets:
            user_ids, group_ids = self._resolve_targets(payload["targets"])
        else:
            user_ids, group_ids = self._target_id_lists(self._crud.list_targets(message.id))
        self._ensure_visibility(message.is_public, user_ids, group_ids)
        self._ensure_time_range(message.start_at, message.expires_at)
        try:
            self._session.add(message)
            if replace_targets:
                self._crud.replace_targets(message.id, user_ids=user_ids, group_ids=group_ids)
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
        return self._projection(message, self._crud.list_targets(message.id))

    def update_status(self, *, message_id: UUID, is_active: bool) -> dict[str, Any]:
        """启用或下架消息。"""

        message = self._require(message_id)
        message.is_active = is_active
        try:
            self._session.add(message)
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
        return self._projection(message, self._crud.list_targets(message.id))

    def delete(self, message_id: UUID) -> None:
        """逻辑删除消息及其定向关系。"""

        message = self._require(message_id)
        try:
            self._crud.soft_delete(message)
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise

    def _require(self, message_id: UUID) -> Message:
        message = self._crud.get(message_id)
        if message is None:
            raise NotFoundError("消息不存在")
        return message

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
        """校验消息至少对全体用户或一个定向目标可见。"""

        if not is_public and not (user_ids or group_ids):
            raise ValidationError("消息必须对全体用户可见或至少有一个定向目标")

    @staticmethod
    def _ensure_time_range(start_at: datetime, expires_at: datetime | None) -> None:
        """校验过期时间必须晚于生效时间。"""

        if expires_at is not None and expires_at <= start_at:
            raise ValidationError("消息过期时间必须晚于生效时间")

    @staticmethod
    def _group_targets(targets: list[MessageTarget]) -> dict[UUID, list[MessageTarget]]:
        grouped: dict[UUID, list[MessageTarget]] = {}
        for target in targets:
            grouped.setdefault(target.message_id, []).append(target)
        return grouped

    @staticmethod
    def _target_id_lists(targets: list[MessageTarget]) -> tuple[list[UUID], list[int]]:
        user_ids = [target.user_id for target in targets if target.user_id is not None]
        group_ids = [target.token_group_id for target in targets if target.token_group_id is not None]
        return user_ids, group_ids

    @classmethod
    def _projection(cls, message: Message, targets: list[MessageTarget]) -> dict[str, Any]:
        user_ids, group_ids = cls._target_id_lists(targets)
        return {
            "id": message.id,
            "title": message.title,
            "content": message.content,
            "type": message.type.value,
            "is_public": message.is_public,
            "is_active": message.is_active,
            "start_at": message.start_at,
            "expires_at": message.expires_at,
            "created_at": message.created_at,
            "updated_at": message.updated_at,
            "targets": {
                "user_ids": user_ids,
                "token_group_ids": group_ids,
            },
        }
