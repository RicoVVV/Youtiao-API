"""Token 分组、授权与绑定关系的数据库访问。"""

from uuid import UUID

from sqlalchemy import func, select, update
from sqlmodel import Session

from app.modules.user.model.token_group import TokenGroup, TokenGroupBinding, TokenGroupUser


class TokenGroupCrud:
    """封装 Token 分组授权和绑定的持久化读写。"""

    def __init__(self, session: Session) -> None:
        """绑定调用方提供的事务会话。"""

        self._session = session

    def create_group(
        self, *, name: str, description: str, visibility: str, is_active: bool, price_multiplier
    ) -> TokenGroup:
        """创建分组并刷新主键，供同一事务继续写入授权关系。"""

        group = TokenGroup(
            name=name,
            description=description,
            visibility=visibility,
            is_active=is_active,
            price_multiplier=price_multiplier,
        )
        self._session.add(group)
        self._session.flush()
        if group.id is None:
            raise RuntimeError("Token 分组主键生成失败")
        return group

    def get_group(self, group_id: int) -> TokenGroup | None:
        """读取未逻辑删除的指定分组。"""

        return self._session.get(TokenGroup, group_id)

    def get_default_group(self) -> TokenGroup | None:
        """读取系统预置的默认分组，供新建模型自动生成默认定价使用。"""

        return self._session.scalar(select(TokenGroup).where(TokenGroup.is_default.is_(True)))

    def list_groups(self) -> list[TokenGroup]:
        """按自增主键稳定列出全部未删除分组。"""

        return list(self._session.scalars(select(TokenGroup).order_by(TokenGroup.id)))

    def list_groups_by_ids(self, group_ids: set[int]) -> list[TokenGroup]:
        """批量读取指定的未删除分组。"""

        if not group_ids:
            return []
        return list(self._session.scalars(select(TokenGroup).where(TokenGroup.id.in_(group_ids))))

    def list_groups_page(self, page: int, page_size: int) -> tuple[int, list[TokenGroup]]:
        """按自增主键分页读取未删除分组及其总数量。"""

        statement = select(TokenGroup)
        total = self._session.scalar(select(func.count()).select_from(TokenGroup)) or 0
        groups = list(
            self._session.scalars(statement.order_by(TokenGroup.id).offset((page - 1) * page_size).limit(page_size))
        )
        return total, groups

    def list_available_groups(self, user_id: UUID) -> list[TokenGroup]:
        """查询用户可选择的启用公开或已授权受限分组。"""

        return list(
            self._session.scalars(
                select(TokenGroup)
                .outerjoin(TokenGroupUser, TokenGroupUser.group_id == TokenGroup.id)
                .where(
                    TokenGroup.is_active.is_(True),
                    (TokenGroup.visibility == "public") | (TokenGroupUser.user_id == user_id),
                )
                .distinct()
                .order_by(TokenGroup.id)
            )
        )

    def list_group_users(self, group_id: int) -> list[UUID]:
        """按稳定顺序列出分组的显式授权用户标识。"""

        return list(
            self._session.scalars(
                select(TokenGroupUser.user_id)
                .where(TokenGroupUser.group_id == group_id)
                .order_by(TokenGroupUser.user_id)
            )
        )

    def replace_group_users(self, group_id: int, user_ids: list[UUID]) -> None:
        """整体替换分组授权关系，保留撤销记录的逻辑删除历史。"""

        existing = list(
            self._session.scalars(
                select(TokenGroupUser)
                .where(TokenGroupUser.group_id == group_id)
                .execution_options(include_deleted=True)
            )
        )
        users_by_id = {item.user_id: item for item in existing}
        self._session.execute(
            update(TokenGroupUser)
            .where(TokenGroupUser.group_id == group_id, TokenGroupUser.is_del.is_(False))
            .values(is_del=True)
        )
        for user_id in user_ids:
            relation = users_by_id.get(user_id)
            if relation is None:
                self._session.add(TokenGroupUser(group_id=group_id, user_id=user_id))
            else:
                relation.is_del = False
        self._session.flush()

    def group_is_available_to_user(self, group_id: int, user_id: UUID) -> bool:
        """实时判断分组启用状态及其对用户的可见权限。"""

        return (
            self._session.scalar(
                select(TokenGroup.id)
                .outerjoin(TokenGroupUser, TokenGroupUser.group_id == TokenGroup.id)
                .where(
                    TokenGroup.id == group_id,
                    TokenGroup.is_active.is_(True),
                    (TokenGroup.visibility == "public") | (TokenGroupUser.user_id == user_id),
                )
            )
            is not None
        )

    def list_bindings(self, token_id: UUID) -> list[tuple[TokenGroupBinding, TokenGroup]]:
        """按优先级读取 Token 的绑定及分组展示信息。"""

        return list(
            self._session.execute(
                select(TokenGroupBinding, TokenGroup)
                .join(TokenGroup, TokenGroup.id == TokenGroupBinding.group_id)
                .where(TokenGroupBinding.token_id == token_id)
                .order_by(TokenGroupBinding.priority, TokenGroupBinding.id)
            ).all()
        )

    def list_runtime_available_bindings(
        self, token_id: UUID, user_id: UUID
    ) -> list[tuple[TokenGroupBinding, TokenGroup]]:
        """读取 Token 已绑定且当前对用户可用的全部分组。"""

        return list(
            self._session.execute(
                select(TokenGroupBinding, TokenGroup)
                .join(TokenGroup, TokenGroup.id == TokenGroupBinding.group_id)
                .outerjoin(
                    TokenGroupUser,
                    (TokenGroupUser.group_id == TokenGroup.id) & (TokenGroupUser.user_id == user_id),
                )
                .where(
                    TokenGroupBinding.token_id == token_id,
                    TokenGroup.is_active.is_(True),
                    (TokenGroup.visibility == "public") | (TokenGroupUser.user_id == user_id),
                )
                .order_by(TokenGroupBinding.priority, TokenGroupBinding.id)
            ).all()
        )

    def replace_bindings(self, token_id: UUID, group_ids: list[int]) -> None:
        """整体替换 Token 分组绑定，并按传入顺序保存优先级。"""

        existing = list(
            self._session.scalars(
                select(TokenGroupBinding)
                .where(TokenGroupBinding.token_id == token_id)
                .execution_options(include_deleted=True)
            )
        )
        bindings_by_group = {item.group_id: item for item in existing}
        self._session.execute(
            update(TokenGroupBinding)
            .where(TokenGroupBinding.token_id == token_id, TokenGroupBinding.is_del.is_(False))
            .values(is_del=True)
        )
        for priority, group_id in enumerate(group_ids):
            binding = bindings_by_group.get(group_id)
            if binding is None:
                self._session.add(TokenGroupBinding(token_id=token_id, group_id=group_id, priority=priority))
            else:
                binding.priority = priority
                binding.is_del = False
        self._session.flush()
