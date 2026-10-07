"""封装每用户模型并发租约的持久化操作。"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlmodel import Session

from app.modules.channels.model.concurrency import UserConcurrencyLease, UserModelConcurrencyOverride
from app.modules.models.model import Model
from app.modules.user.model.user import User


class ConcurrencyCrud:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_lease_by_task_id(self, *, task_id: UUID) -> UserConcurrencyLease | None:
        return self._session.scalar(select(UserConcurrencyLease).where(UserConcurrencyLease.task_id == task_id))

    def lock_user(self, *, user_id: UUID) -> None:
        self._session.scalar(select(User).where(User.id == user_id).with_for_update())

    def get_model_and_override_for_update(
        self, *, user_id: UUID, model_id: UUID
    ) -> tuple[Model | None, UserModelConcurrencyOverride | None]:
        model = self._session.scalar(select(Model).where(Model.id == model_id))
        override = self._session.scalar(
            select(UserModelConcurrencyOverride)
            .where(UserModelConcurrencyOverride.user_id == user_id, UserModelConcurrencyOverride.model_id == model_id)
            .with_for_update()
        )
        return model, override

    def count_active_leases(self, *, user_id: UUID, model_id: UUID) -> int:
        return int(
            self._session.scalar(
                select(func.count())
                .select_from(UserConcurrencyLease)
                .where(
                    UserConcurrencyLease.user_id == user_id,
                    UserConcurrencyLease.model_id == model_id,
                    UserConcurrencyLease.released_at.is_(None),
                )
            )
            or 0
        )

    def create_lease(self, *, task_id: UUID, user_id: UUID, model_id: UUID) -> None:
        self._session.add(UserConcurrencyLease(task_id=task_id, user_id=user_id, model_id=model_id))

    def get_lease_by_task_id_for_update(self, *, task_id: UUID) -> UserConcurrencyLease | None:
        return self._session.scalar(
            select(UserConcurrencyLease).where(UserConcurrencyLease.task_id == task_id).with_for_update()
        )

    def release_lease(self, *, lease: UserConcurrencyLease, released_at: datetime) -> None:
        lease.released_at = released_at
