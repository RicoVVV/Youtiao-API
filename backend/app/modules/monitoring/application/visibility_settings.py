"""用户侧监控可见范围的管理用例。

管理员可限制用户在监控页看到哪些 Token 分组与请求类型；未开启限制时保持原有行为，
用户可见其全部分组与 text/image/video 三种类型。
"""

from sqlmodel import Session

from app.core.errors import ValidationError
from app.modules.channels.crud.channels import ChannelCrud
from app.modules.monitoring.crud.snapshot_crud import TRACKED_REQUEST_TYPES
from app.modules.monitoring.crud.visibility_crud import MonitorUserVisibilityCrud
from app.modules.user.crud.token_group_crud import TokenGroupCrud


class MonitorUserVisibilityApplicationService:
    """维护用户侧监控可见范围配置，并向查询用例提供过滤条件。"""

    def __init__(self, session: Session) -> None:
        """绑定调用方提供的事务会话。"""

        self._session = session
        self._visibility = MonitorUserVisibilityCrud(session)
        self._groups = TokenGroupCrud(session)
        self._channels = ChannelCrud(session)

    def restricted_group_ids(self) -> set[int] | None:
        """返回允许用户看到的分组标识；``None`` 表示不限制。"""

        record = self._visibility.get()
        if record is None or not record.enabled:
            return None
        return {int(group_id) for group_id in record.group_ids}

    def visible_request_types(self) -> tuple[str, ...]:
        """返回允许用户看到的请求类型，按固定顺序排列。"""

        record = self._visibility.get()
        if record is None or not record.enabled:
            return TRACKED_REQUEST_TYPES
        allowed = {str(request_type) for request_type in record.request_types}
        visible = tuple(request_type for request_type in TRACKED_REQUEST_TYPES if request_type in allowed)
        return visible or TRACKED_REQUEST_TYPES

    def view(self) -> dict:
        """返回管理视图，并附带每个分组当前支持的请求类型供前端联动筛选。"""

        record = self._visibility.get()
        groups = self._groups.list_groups()
        supported = self._channels.list_group_model_types(group_ids=[group.id for group in groups])
        group_options = [
            {
                "id": group.id,
                "name": group.name,
                "is_active": group.is_active,
                "request_types": [
                    request_type
                    for request_type in TRACKED_REQUEST_TYPES
                    if request_type in set(supported.get(group.id, []))
                ],
            }
            for group in groups
        ]
        if record is None or not record.enabled:
            return {
                "enabled": False,
                "group_ids": [],
                "request_types": list(TRACKED_REQUEST_TYPES),
                "groups": group_options,
                "updated_at": record.updated_at.isoformat() if record is not None and record.updated_at else None,
            }
        return {
            "enabled": True,
            "group_ids": [int(group_id) for group_id in record.group_ids],
            "request_types": [str(request_type) for request_type in record.request_types],
            "groups": group_options,
            "updated_at": record.updated_at.isoformat() if record.updated_at is not None else None,
        }

    def update(self, payload: dict) -> dict:
        """更新可见范围配置；开启限制时必须同时选择至少一个分组与一种请求类型。"""

        enabled = bool(payload.get("enabled", False))
        group_ids = sorted({int(group_id) for group_id in payload.get("group_ids") or []})
        requested_types = [str(request_type) for request_type in payload.get("request_types") or []]
        invalid_types = [item for item in requested_types if item not in TRACKED_REQUEST_TYPES]
        if invalid_types:
            raise ValidationError("不支持的请求类型")
        request_types = [item for item in TRACKED_REQUEST_TYPES if item in set(requested_types)]
        if enabled:
            if not group_ids:
                raise ValidationError("开启可见范围限制时至少选择一个分组")
            if not request_types:
                raise ValidationError("开启可见范围限制时至少选择一种请求类型")
            existing = {group.id for group in self._groups.list_groups_by_ids(set(group_ids))}
            if any(group_id not in existing for group_id in group_ids):
                raise ValidationError("Token 分组不存在")
        else:
            # 不限制时清空分组白名单并把类型恢复为全部，避免关闭限制后仍残留旧选择。
            group_ids = []
            request_types = list(TRACKED_REQUEST_TYPES)
        values = {"enabled": enabled, "group_ids": group_ids, "request_types": request_types}
        try:
            record = self._visibility.get()
            if record is None:
                self._visibility.create(values)
            else:
                self._visibility.update(record, values)
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
        return self.view()
