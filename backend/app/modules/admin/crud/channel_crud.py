from typing import Any
from uuid import UUID

from sqlalchemy import Integer, cast, exists, func, or_, update
from sqlalchemy import select as sqlalchemy_select
from sqlmodel import Session, select

from app.modules.channels.model.channel import Channel
from app.modules.user.model.token_group import TokenGroup


def _jsonb_text_elements(column: Any) -> Any:
    """把 JSONB 文本数组展开成可关联的集合，用于按数组元素做模糊匹配。"""

    return func.jsonb_array_elements_text(column).table_valued("value")


def _any_element_matches(column: Any, pattern: str) -> Any:
    """判断 JSONB 文本数组是否存在模糊命中 pattern 的元素。"""

    elements = _jsonb_text_elements(column)
    return exists(select(1).select_from(elements).where(elements.c.value.ilike(pattern)))


def _token_group_name_matches(pattern: str) -> Any:
    """判断渠道绑定的分组中是否存在名称模糊命中 pattern 的分组。"""

    group_ids = _jsonb_text_elements(Channel.token_group_ids)
    return exists(
        select(1)
        .select_from(group_ids)
        .join(TokenGroup, cast(group_ids.c.value, Integer) == TokenGroup.id)
        .where(TokenGroup.name.ilike(pattern))
    )


class ChannelCrud:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, channel: Channel) -> None:
        self._session.add(channel)

    def flush(self) -> None:
        self._session.flush()

    def get(self, channel_id: UUID) -> Channel | None:
        return self._session.get(Channel, channel_id)

    def get_for_update(self, channel_id: UUID) -> Channel | None:
        return self._session.scalar(sqlalchemy_select(Channel).where(Channel.id == channel_id).with_for_update())

    def update_latest_test_snapshot(self, *, channel_id: UUID, snapshot: dict[str, object]) -> bool:
        channel = self.get_for_update(channel_id)
        if channel is None:
            return False
        channel.latest_test_snapshot = dict(snapshot)
        return True

    def exists_name(self, name: str) -> bool:
        return self._session.scalar(select(Channel.id).where(Channel.name == name)) is not None

    def list_page(
        self,
        *,
        channel_name: str | None,
        model_name: str | None,
        token_group_name: str | None,
        page: int,
        page_size: int,
    ) -> tuple[int, list[Channel]]:
        filters: list[Any] = []
        if channel_name:
            filters.append(Channel.name.ilike(f"%{channel_name}%"))
        if model_name:
            filters.append(_any_element_matches(Channel.supported_models, f"%{model_name}%"))
        if token_group_name:
            filters.append(_token_group_name_matches(f"%{token_group_name}%"))
        statement = select(Channel)
        count_statement = select(func.count()).select_from(Channel)
        for condition in filters:
            statement = statement.where(condition)
            count_statement = count_statement.where(condition)
        total = self._session.scalar(count_statement) or 0
        items = list(
            self._session.exec(
                statement.order_by(Channel.created_at.desc(), Channel.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        return total, items

    def list_referencing_model(self, model_name: str) -> list[Channel]:
        return list(
            self._session.exec(
                select(Channel).where(
                    Channel.is_del.is_(False),
                    or_(
                        Channel.supported_models.contains([model_name]),
                        Channel.model_mapping.op("?")(model_name),
                    ),
                )
            )
        )

    def soft_delete_bindings(self, channel_id: UUID) -> None:
        from app.modules.models.model import ModelRoute

        self._session.execute(update(ModelRoute).where(ModelRoute.channel_id == channel_id).values(is_del=True))
