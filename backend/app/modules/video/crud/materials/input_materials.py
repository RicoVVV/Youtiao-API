from collections.abc import Iterable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.video.model.input_material import VideoInputMaterial


class InputMaterialCrud:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_many(self, materials: Iterable[VideoInputMaterial]) -> None:
        self._session.add_all(list(materials))

    def list_by_task(self, *, task_id: UUID) -> list[VideoInputMaterial]:
        return list(
            self._session.scalars(
                select(VideoInputMaterial)
                .where(VideoInputMaterial.task_id == task_id)
                .order_by(VideoInputMaterial.field_name, VideoInputMaterial.position)
            )
        )
