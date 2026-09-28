from uuid import UUID

from sqlalchemy import func, or_, update
from sqlalchemy import select as sqlalchemy_select
from sqlmodel import Session, select

from app.modules.models.model.model import Model
from app.modules.pricing.model.pricing import PricingRule


class PricingRuleCrud:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, rule: PricingRule) -> None:
        self._session.add(rule)

    def flush(self) -> None:
        self._session.flush()

    def get(self, rule_id: UUID) -> PricingRule | None:
        return self._session.get(PricingRule, rule_id)

    def get_for_update(self, rule_id: UUID) -> PricingRule | None:
        return self._session.scalar(sqlalchemy_select(PricingRule).where(PricingRule.id == rule_id).with_for_update())

    def max_priority(self, *, model_id: UUID, token_group_id: int) -> int | None:
        return self._session.scalar(
            select(func.max(PricingRule.priority)).where(
                PricingRule.model_id == model_id,
                PricingRule.token_group_id == token_group_id,
            )
        )

    def exists_name(self, *, model_id: UUID, token_group_id: int, name: str) -> bool:
        return (
            self._session.scalar(
                select(PricingRule.id).where(
                    PricingRule.model_id == model_id,
                    PricingRule.token_group_id == token_group_id,
                    PricingRule.name == name,
                )
            )
            is not None
        )

    def has_priority_conflict(
        self, *, model_id: UUID, token_group_id: int, priority: int, exclude_rule_id: UUID | None = None
    ) -> bool:
        statement = select(PricingRule.id).where(
            PricingRule.model_id == model_id,
            PricingRule.token_group_id == token_group_id,
            PricingRule.priority == priority,
        )
        if exclude_rule_id is not None:
            statement = statement.where(PricingRule.id != exclude_rule_id)
        return self._session.scalar(statement) is not None

    def list_page(
        self, *, model_id: UUID | None, keyword: str | None, page: int, page_size: int
    ) -> tuple[int, list[PricingRule]]:
        statement = select(PricingRule)
        count_statement = select(func.count()).select_from(PricingRule)
        if model_id is not None:
            statement = statement.where(PricingRule.model_id == model_id)
            count_statement = count_statement.where(PricingRule.model_id == model_id)
        if keyword:
            pattern = f"%{keyword}%"
            keyword_filter = or_(
                PricingRule.name.ilike(pattern),
                PricingRule.model_id.in_(select(Model.id).where(Model.name.ilike(pattern))),
            )
            statement = statement.where(keyword_filter)
            count_statement = count_statement.where(keyword_filter)
        total = self._session.scalar(count_statement) or 0
        items = list(
            self._session.exec(
                statement.order_by(PricingRule.token_group_id, PricingRule.priority, PricingRule.id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        return total, items

    def list_for_model(self, model_id: UUID) -> list[PricingRule]:
        return list(
            self._session.exec(
                select(PricingRule)
                .where(PricingRule.model_id == model_id)
                .order_by(PricingRule.token_group_id, PricingRule.priority)
            )
        )

    def soft_delete_for_model(self, model_id: UUID) -> None:
        self._session.execute(
            update(PricingRule)
            .where(PricingRule.model_id == model_id, PricingRule.is_del.is_(False))
            .values(is_del=True)
        )
