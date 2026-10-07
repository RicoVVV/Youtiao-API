"""长期 Token 数据库操作。"""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func
from sqlalchemy import select as sqlalchemy_select
from sqlmodel import Session, select

from app.modules.user.model.token import Token


class TokenCrud:
    """封装长期 Token 的归属查询、签发和撤销操作。"""

    def __init__(self, session: Session) -> None:
        """绑定外部传入的数据库会话。"""

        self._session = session

    def list_by_user(self, user_id: UUID) -> list[Token]:
        """按创建时间倒序查询用户全部 Token 实体。"""

        return list(self._session.exec(select(Token).where(Token.user_id == user_id).order_by(Token.created_at.desc())))

    def list_page_by_user(self, user_id: UUID, page: int, page_size: int) -> tuple[int, list[Token]]:
        """分页查询指定用户的 Token，返回总数和按稳定顺序排列的当前页实体。"""

        total = int(self._session.scalar(sqlalchemy_select(func.count(Token.id)).where(Token.user_id == user_id)) or 0)
        statement = (
            select(Token)
            .where(Token.user_id == user_id)
            .order_by(Token.created_at.desc(), Token.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return total, list(self._session.exec(statement))

    def get_by_user(self, token_id: UUID, user_id: UUID) -> Token | None:
        """按 Token 和用户归属查询单条记录。"""

        return self._session.exec(select(Token).where(Token.id == token_id, Token.user_id == user_id)).first()

    def count_active_by_user(self, user_id: UUID) -> int:
        """统计用户当前可用的 Token 数量，禁用凭证不占用签发上限。"""

        return int(
            self._session.scalar(
                sqlalchemy_select(func.count(Token.id)).where(Token.user_id == user_id, Token.is_active.is_(True))
            )
            or 0
        )

    def create(self, *, user_id: UUID, token: str, label: str | None) -> Token:
        """保存完整 Token 明文并返回持久化实体。"""

        item = Token(user_id=user_id, token=token, label=label)
        self._session.add(item)
        self._session.flush()
        return item

    def soft_delete(self, token_id: UUID, user_id: UUID) -> Token | None:
        """软删除指定用户的 Token，删除后不再参与常规查询且不可恢复。"""

        item = self._session.exec(select(Token).where(Token.id == token_id, Token.user_id == user_id)).first()
        if item is None:
            return None
        item.is_del = True
        return item

    def set_active(self, token_id: UUID, user_id: UUID, is_active: bool) -> Token | None:
        """设置指定用户 Token 的启用状态，调用方负责提交事务。"""

        item = self._session.exec(select(Token).where(Token.id == token_id, Token.user_id == user_id)).first()
        if item is None:
            return None
        item.is_active = is_active
        return item

    def authenticate(self, token_value: str) -> Token | None:
        """查询可用 Token 并更新最近使用时间，调用方负责提交事务。"""

        item = self._session.exec(select(Token).where(Token.token == token_value, Token.is_active.is_(True))).first()
        if item is not None:
            item.last_used_at = datetime.now(UTC)
        return item
