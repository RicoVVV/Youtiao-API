"""分组与渠道展示名的批量查询。

告警文案与运维视图需要用名称展示分组和渠道，本模块只提供批量名称映射，
避免逐行查询造成 N+1；已逻辑删除的分组与渠道同样返回名称，保证历史数据可读。
"""

from uuid import UUID

from sqlalchemy import select
from sqlmodel import Session

from app.modules.channels.model.channel import Channel
from app.modules.user.model.token_group import TokenGroup


class MonitoringReferenceCrud:
    """封装分组与渠道标识到名称的批量映射。"""

    def __init__(self, session: Session) -> None:
        """绑定调用方提供的事务会话。"""

        self._session = session

    def group_names(self, group_ids: set[int]) -> dict[int, str]:
        """批量读取分组名称。"""

        if not group_ids:
            return {}
        rows = self._session.execute(
            select(TokenGroup.id, TokenGroup.name)
            .where(TokenGroup.id.in_(group_ids))
            .execution_options(include_deleted=True)
        ).all()
        return {int(group_id): name for group_id, name in rows}

    def channel_names(self, channel_ids: set[UUID]) -> dict[UUID, str]:
        """批量读取渠道名称。"""

        if not channel_ids:
            return {}
        rows = self._session.execute(
            select(Channel.id, Channel.name).where(Channel.id.in_(channel_ids)).execution_options(include_deleted=True)
        ).all()
        return {channel_id: name for channel_id, name in rows}
