"""提供管理员用户模型并发覆盖的校验与持久化服务。"""

from uuid import UUID

from sqlmodel import Session

from app.core.errors import NotFoundError
from app.modules.admin.crud.concurrency_crud import ConcurrencyCrud
from app.modules.channels.model.concurrency import UserModelConcurrencyOverride
from app.modules.user.crud.user_crud import UserCrud


class AdminConcurrencyApplicationService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._crud = ConcurrencyCrud(session)
        self._users = UserCrud(session)

    def save_override(
        self, *, user_id: UUID, model_id: UUID, concurrency_limit: int, active: bool
    ) -> UserModelConcurrencyOverride:
        try:
            if self._users.get_by_id(user_id) is None:
                raise NotFoundError("用户不存在")
            if not self._crud.model_exists(model_id):
                raise NotFoundError("模型不存在")
            override = self._crud.get_override_for_update(user_id=user_id, model_id=model_id)
            if override is None:
                override = self._crud.create_override(user_id=user_id, model_id=model_id)
            override.concurrency_limit = concurrency_limit
            override.active = active
            self._crud.flush()
            self._session.commit()
            return override
        except Exception:
            self._session.rollback()
            raise

    def user_model_usage(self, *, user_id: UUID) -> dict:
        if self._users.get_by_id(user_id) is None:
            raise NotFoundError("用户不存在")
        return {
            "user_id": user_id,
            "items": self._crud.list_overrides(user_id=user_id),
            "active_lease_counts": self._crud.count_active_leases_by_model(user_id=user_id),
        }
