"""长期 Token 应用服务，编排签发、查询、软删除和启停等业务用例。"""

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlmodel import Session

from app.core.errors import NotFoundError, ValidationError
from app.modules.user.application.token.contracts import RuntimeTokenGroups, TokenData, TokenGroupData, TokenPage
from app.modules.user.crud.token_crud import TokenCrud
from app.modules.user.crud.token_group_crud import TokenGroupCrud
from app.modules.user.crud.user_crud import UserCrud
from app.modules.user.model.token import Token
from app.modules.user.security.token_secret import generate_token


@dataclass(frozen=True, slots=True)
class TokenSecret:
    """创建后返回的长期 Token 明文。"""

    raw_value: str


class TokenApplicationService:
    """处理长期 Token 生命周期的事务型应用用例。"""

    def __init__(self, session: Session) -> None:
        """接收调用方管理的 Session，应用层不自行提交事务。"""

        self._session = session
        self._tokens = TokenCrud(session)
        self._groups = TokenGroupCrud(session)
        self._users = UserCrud(session)

    def list_tokens(self, user_id: UUID) -> list[TokenData]:
        """返回指定用户的全部 Token，由仓储完成持久化查询。"""

        return [self._to_token_data(item) for item in self._tokens.list_by_user(user_id)]

    def list_tokens_page(self, user_id: UUID, page: int, page_size: int) -> TokenPage:
        """分页返回指定用户的 Token 投影和总数量。"""

        total, tokens = self._tokens.list_page_by_user(user_id, page, page_size)
        return TokenPage(tokens=[self._to_token_data(item) for item in tokens], total=total)

    def copy_token(self, user_id: UUID, token_id: UUID) -> str:
        token = self._tokens.get_by_user(token_id, user_id)
        if token is None:
            raise NotFoundError("Token 不存在")
        return token.token

    def issue_token(
        self, *, user_id: UUID, label: str | None, group_ids: list[int] | None = None
    ) -> tuple[TokenData, TokenSecret]:
        """向既有用户签发附加长期 Token，且不重复创建钱包。"""

        active_token_count = self._tokens.count_active_by_user(user_id)
        if active_token_count >= 10:
            raise ValidationError("可用 Token 数量已达上限")
        if group_ids is not None:
            self._validate_group_ids(user_id, group_ids)
        raw_value = generate_token()
        token = self._tokens.create(user_id=user_id, token=raw_value, label=label)
        if group_ids is not None:
            self._groups.replace_bindings(token.id, group_ids)
        else:
            return (
                TokenData(
                    id=token.id,
                    user_id=token.user_id,
                    token=token.token,
                    label=token.label,
                    created_at=token.created_at,
                    last_used_at=token.last_used_at,
                    is_del=token.is_del,
                    is_active=token.is_active,
                ),
                TokenSecret(raw_value),
            )
        return self._to_token_data(token), TokenSecret(raw_value)

    def create_token(self, *, user_id: UUID, label: str | None, group_ids: list[int]) -> TokenData:
        try:
            token, _ = self.issue_token(user_id=user_id, label=label, group_ids=group_ids)
            self._session.commit()
            return token
        except Exception:
            self._session.rollback()
            raise

    def issue_token_for_existing_user(
        self, *, user_id: UUID, label: str | None, group_ids: list[int] | None = None
    ) -> tuple[TokenData, TokenSecret]:
        """为存在的目标用户签发长期 Token，避免 API 层直接访问 ORM。

        参数：user_id 为待签发用户标识，label 为可选展示标签。
        返回值：新 Token 的安全投影和仅本次返回的明文值。
        异常/副作用：用户不存在时抛出 ValueError；成功时将 Token 加入当前事务但不提交。
        """

        if self._users.get_by_id(user_id) is None:
            raise NotFoundError("用户不存在")
        try:
            result = self.issue_token(user_id=user_id, label=label, group_ids=group_ids)
            self._session.commit()
            return result
        except Exception:
            self._session.rollback()
            raise

    def delete_token(self, user_id: UUID, token_id: UUID) -> TokenData:
        """软删除当前用户拥有的长期 Token，不存在时拒绝该请求。"""

        try:
            token = self._tokens.soft_delete(token_id, user_id)
            if token is None:
                raise NotFoundError("Token 不存在")
            self._session.commit()
            return self._to_token_data(token)
        except Exception:
            self._session.rollback()
            raise

    def set_token_active(self, user_id: UUID, token_id: UUID, is_active: bool) -> TokenData:
        """启用或禁用当前用户拥有的 Token，不存在时拒绝该请求。"""

        try:
            token = self._tokens.set_active(token_id, user_id, is_active)
            if token is None:
                raise NotFoundError("Token 不存在")
            self._session.commit()
            return self._to_token_data(token)
        except Exception:
            self._session.rollback()
            raise

    def replace_token_groups(self, *, user_id: UUID, token_id: UUID, group_ids: list[int]) -> TokenData:
        """整体替换当前用户 Token 的分组绑定，并以请求顺序写入优先级。"""

        try:
            token = self._tokens.get_by_user(token_id, user_id)
            if token is None:
                raise NotFoundError("Token 不存在")
            self._validate_group_ids(user_id, group_ids)
            self._groups.replace_bindings(token.id, group_ids)
            self._session.commit()
            return self._to_token_data(token)
        except Exception:
            self._session.rollback()
            raise

    def list_available_groups(self, user_id: UUID) -> list[TokenGroupData]:
        """返回当前用户可选择的启用分组安全投影。"""

        return [self._to_group_data(group) for group in self._groups.list_available_groups(user_id)]

    def get_runtime_groups(self, *, token_id: UUID, user_id: UUID) -> RuntimeTokenGroups:
        """读取 Token 全部当前有效分组，失效绑定只过滤且空结果拒绝。"""

        bindings = self._groups.list_runtime_available_bindings(token_id, user_id)
        if not bindings:
            raise ValidationError("当前分组不可用")
        return RuntimeTokenGroups(
            token_id=token_id,
            user_id=user_id,
            groups=[self._to_group_data(group, binding.priority) for binding, group in bindings],
        )

    def _validate_group_ids(self, user_id: UUID, group_ids: list[int]) -> None:
        """校验绑定列表非空、无重复且每个分组对当前用户实时可用。"""

        if not group_ids:
            raise ValidationError("至少绑定一个分组")
        if len(set(group_ids)) != len(group_ids):
            raise ValidationError("分组不可重复")
        if any(not self._groups.group_is_available_to_user(group_id, user_id) for group_id in group_ids):
            raise ValidationError("存在不可用分组")

    def _to_token_data(self, item: Token) -> TokenData:
        """将 Token 及其有序绑定转换为用户可见投影。"""

        return TokenData(
            id=item.id,
            user_id=item.user_id,
            token=item.token,
            label=item.label,
            created_at=item.created_at,
            last_used_at=item.last_used_at,
            is_del=item.is_del,
            is_active=item.is_active,
            groups=[
                self._to_group_data(group, binding.priority) for binding, group in self._groups.list_bindings(item.id)
            ],
        )

    @staticmethod
    def _to_group_data(group, priority: int | None = None) -> TokenGroupData:
        """转换分组 ORM 实体为不包含授权用户的安全投影。"""

        return TokenGroupData(
            id=group.id,
            name=group.name,
            visibility=group.visibility,
            is_active=group.is_active,
            description=getattr(group, "description", ""),
            price_multiplier=getattr(group, "price_multiplier", Decimal("1.000000")),
            priority=priority,
        )
