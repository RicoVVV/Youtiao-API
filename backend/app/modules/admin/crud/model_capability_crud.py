from uuid import UUID

from sqlalchemy import update
from sqlmodel import Session, select

from app.modules.models.model import ModelRoute


class ModelRouteCrud:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, route: ModelRoute) -> None:
        self._session.add(route)

    def list_for_channel(self, channel_id: UUID) -> list[ModelRoute]:
        return list(
            self._session.exec(
                select(ModelRoute).where(ModelRoute.channel_id == channel_id).execution_options(include_deleted=True)
            )
        )

    def soft_delete_for_model(self, model_id: UUID) -> None:
        self._session.execute(
            update(ModelRoute).where(ModelRoute.model_id == model_id, ModelRoute.is_del.is_(False)).values(is_del=True)
        )

    def list_channel_ids_for_model(self, model_id: UUID) -> list[UUID]:
        return list(self._session.exec(select(ModelRoute.channel_id).where(ModelRoute.model_id == model_id).distinct()))
