"""管理员 Token 分组应用服务，协调分组、授权和用户存在性校验。"""

from decimal import Decimal
from uuid import UUID

from sqlmodel import Session

from app.core.errors import NotFoundError, ValidationError
from app.modules.user.crud.token_group_crud import TokenGroupCrud
from app.modules.user.crud.user_crud import UserCrud
from app.modules.user.model.token_group import TokenGroup


class AdminTokenGroupApplicationService:
    """提供管理员维护 Token 分组与受限授权关系的事务用例。"""

    def __init__(self, session: Session) -> None:
        """绑定请求会话并初始化所需的用户和分组仓储。"""

        self._session = session
        self._groups = TokenGroupCrud(session)
        self._users = UserCrud(session)

    def list_groups_page(self, page: int, page_size: int) -> tuple[int, list[dict]]:
        """按自增主键分页列出全部未删除分组和其显式授权用户。"""

        total, groups = self._groups.list_groups_page(page, page_size)
        return total, [self._to_view(group) for group in groups]

    def get_group(self, group_id: int) -> dict:
        """返回指定未删除分组的管理投影，不存在时拒绝请求。"""

        group = self._require_group(group_id)
        return self._to_view(group)

    def create_group(
        self,
        *,
        name: str,
        description: str,
        visibility: str,
        is_active: bool,
        price_multiplier: Decimal,
        user_ids: list[UUID],
    ) -> dict:
        """创建分组并在受限场景整体写入已校验的用户授权。"""

        try:
            self._validate_user_ids(user_ids)
            if visibility == "public" and user_ids:
                raise ValidationError("公开分组不能配置授权用户")
            group = self._groups.create_group(
                name=name,
                description=description,
                visibility=visibility,
                is_active=is_active,
                price_multiplier=price_multiplier,
            )
            if visibility == "restricted":
                self._groups.replace_group_users(group.id, user_ids)
            result = self._to_view(group)
            self._session.commit()
            return result
        except Exception:
            self._session.rollback()
            raise

    def update_group(
        self,
        *,
        group_id: int,
        name: str | None,
        description: str | None,
        visibility: str | None,
        is_active: bool | None,
        price_multiplier: Decimal | None,
        user_ids: list[UUID] | None,
    ) -> dict:
        """按显式字段更新分组，并在携带用户列表时整体替换受限分组授权。

        参数：group_id 为目标分组标识，其余参数为可选更新字段，user_ids 为可选完整授权列表。
        返回值：更新后的分组管理投影。
        异常：分组不存在、公开分组配置授权用户或授权用户无效时抛出 ValueError。
        """

        try:
            group = self._require_group(group_id)
            self._validate_default_group_update(group, name=name, visibility=visibility, is_active=is_active)
            target_visibility = visibility if visibility is not None else group.visibility
            if target_visibility == "public" and user_ids:
                raise ValidationError("公开分组不能配置授权用户")
            if user_ids is not None:
                self._validate_user_ids(user_ids)
            if name is not None:
                group.name = name
            if description is not None:
                group.description = description
            if visibility is not None:
                group.visibility = visibility
            if is_active is not None:
                group.is_active = is_active
            if price_multiplier is not None:
                group.price_multiplier = price_multiplier
            if target_visibility == "public":
                self._groups.replace_group_users(group_id, [])
            elif user_ids is not None:
                self._groups.replace_group_users(group_id, user_ids)
            result = self._to_view(group)
            self._session.commit()
            return result
        except Exception:
            self._session.rollback()
            raise

    def delete_group(self, group_id: int) -> None:
        """逻辑删除分组，不删除历史 Token 绑定以便审计与恢复。"""

        try:
            group = self._require_group(group_id)
            if group.is_default:
                raise ValidationError("默认分组不可删除")
            group.is_del = True
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise

    def _require_group(self, group_id: int) -> TokenGroup:
        """读取分组并将缺失情况映射为统一业务错误。"""

        group = self._groups.get_group(group_id)
        if group is None:
            raise NotFoundError("Token 分组不存在")
        return group

    def _validate_user_ids(self, user_ids: list[UUID]) -> None:
        """校验授权用户列表无重复且所有用户均存在。"""

        if len(set(user_ids)) != len(user_ids):
            raise ValidationError("授权用户不可重复")
        if any(self._users.get_by_id(user_id) is None for user_id in user_ids):
            raise ValidationError("授权用户不存在")

    @staticmethod
    def _validate_default_group_update(
        group: TokenGroup, *, name: str | None, visibility: str | None, is_active: bool | None
    ) -> None:
        if not group.is_default:
            return
        if name is not None and name != group.name:
            raise ValidationError("默认分组不可重命名")
        if visibility is not None and visibility != "public":
            raise ValidationError("默认分组必须公开")
        if is_active is False:
            raise ValidationError("默认分组必须启用")

    def _to_view(self, group: TokenGroup) -> dict:
        """构建包含授权用户展示信息的管理员分组投影。"""

        user_ids = self._groups.list_group_users(group.id)
        return {
            "id": group.id,
            "name": group.name,
            "description": group.description,
            "visibility": group.visibility,
            "is_active": group.is_active,
            "is_default": group.is_default,
            "price_multiplier": group.price_multiplier,
            "users": [{"id": user.id, "username": user.username} for user in self._users.list_by_ids(user_ids)],
        }
