from uuid import UUID

from sqlalchemy import func
from sqlalchemy import select as sqlalchemy_select
from sqlmodel import Session, select

from app.modules.models.model import Model


class ModelCrud:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, model: Model) -> None:
        self._session.add(model)

    def flush(self) -> None:
        self._session.flush()

    def get(self, model_id: UUID) -> Model | None:
        return self._session.get(Model, model_id)

    def get_for_update(self, model_id: UUID) -> Model | None:
        return self._session.scalar(sqlalchemy_select(Model).where(Model.id == model_id).with_for_update())

    def get_including_deleted(self, model_id: UUID) -> Model | None:
        """读取包含逻辑删除记录的模型，供错误提示区分「已删除」与「不存在」。"""

        return self._session.scalar(select(Model).where(Model.id == model_id).execution_options(include_deleted=True))

    def get_by_name(self, name: str, *, exclude_model_id: UUID | None = None) -> Model | None:
        statement = select(Model).where(Model.name == name)
        if exclude_model_id is not None:
            statement = statement.where(Model.id != exclude_model_id)
        return self._session.scalar(statement)

    def list_by_names(self, names: list[str]) -> list[Model]:
        if not names:
            return []
        return list(self._session.exec(select(Model).where(Model.name.in_(names))))

    def list_page(
        self, *, model_name: str | None, template_ids: list[str] | None, page: int, page_size: int
    ) -> tuple[int, list[Model]]:
        statement = select(Model)
        count_statement = select(func.count()).select_from(Model)
        if model_name:
            name_filter = Model.name.ilike(f"%{model_name}%")
            statement = statement.where(name_filter)
            count_statement = count_statement.where(name_filter)
        if template_ids is not None:
            statement = statement.where(Model.template_id.in_(template_ids))
            count_statement = count_statement.where(Model.template_id.in_(template_ids))
        total = self._session.scalar(count_statement) or 0
        items = list(
            self._session.exec(
                statement.order_by(Model.created_at.desc(), Model.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        return total, items
