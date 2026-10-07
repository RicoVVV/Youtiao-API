"""封装管理员用户模型并发覆盖的数据库访问。"""

from uuid import UUID

from sqlalchemy import func, select
from sqlmodel import Session

from app.modules.channels.model.concurrency import UserConcurrencyLease, UserModelConcurrencyOverride
from app.modules.models.model import Model


class ConcurrencyCrud:
    """封装管理员并发管理资源的持久化操作。"""

    def __init__(self, session: Session) -> None:
        """绑定调用方提供的事务会话。"""

        self._session = session

    def model_exists(self, model_id: UUID) -> bool:
        """判断模型是否存在。"""

        return self._session.get(Model, model_id) is not None

    def get_override_for_update(self, *, user_id: UUID, model_id: UUID) -> UserModelConcurrencyOverride | None:
        """锁定并读取用户针对指定模型的覆盖记录。"""

        return self._session.scalar(
            select(UserModelConcurrencyOverride)
            .where(
                UserModelConcurrencyOverride.user_id == user_id,
                UserModelConcurrencyOverride.model_id == model_id,
            )
            .with_for_update()
        )

    def create_override(self, *, user_id: UUID, model_id: UUID) -> UserModelConcurrencyOverride:
        """创建尚未设置可变属性的用户模型并发覆盖。"""

        override = UserModelConcurrencyOverride(user_id=user_id, model_id=model_id, concurrency_limit=0)
        self._session.add(override)
        return override

    def flush(self) -> None:
        """刷新当前并发配置写入，供应用服务在提交前取得数据库生成值。"""

        self._session.flush()

    def list_overrides(self, *, user_id: UUID) -> list[UserModelConcurrencyOverride]:
        """按创建顺序列出用户全部模型并发覆盖。"""

        return list(
            self._session.scalars(
                select(UserModelConcurrencyOverride)
                .where(UserModelConcurrencyOverride.user_id == user_id)
                .order_by(UserModelConcurrencyOverride.created_at)
            )
        )

    def count_active_leases_by_model(self, *, user_id: UUID) -> dict[UUID, int]:
        """统计用户在每个模型下尚未释放的租约数量。"""

        return dict(
            self._session.execute(
                select(UserConcurrencyLease.model_id, func.count())
                .where(UserConcurrencyLease.user_id == user_id, UserConcurrencyLease.released_at.is_(None))
                .group_by(UserConcurrencyLease.model_id)
            ).all()
        )
