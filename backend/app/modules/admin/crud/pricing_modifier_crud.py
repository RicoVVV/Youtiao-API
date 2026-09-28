from uuid import UUID

from sqlalchemy import func, update
from sqlalchemy import select as sqlalchemy_select
from sqlmodel import Session, select

from app.modules.pricing.model.pricing import PricingModifier


class PricingModifierCrud:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, modifier: PricingModifier) -> None:
        self._session.add(modifier)

    def get(self, modifier_id: UUID) -> PricingModifier | None:
        return self._session.get(PricingModifier, modifier_id)

    def get_for_update(self, modifier_id: UUID) -> PricingModifier | None:
        return self._session.scalar(
            sqlalchemy_select(PricingModifier).where(PricingModifier.id == modifier_id).with_for_update()
        )

    def max_priority(self, *, pricing_rule_id: UUID) -> int | None:
        return self._session.scalar(
            select(func.max(PricingModifier.priority)).where(PricingModifier.pricing_rule_id == pricing_rule_id)
        )

    def exists_name(self, *, pricing_rule_id: UUID, name: str) -> bool:
        return (
            self._session.scalar(
                select(PricingModifier.id).where(
                    PricingModifier.pricing_rule_id == pricing_rule_id,
                    PricingModifier.name == name,
                )
            )
            is not None
        )

    def has_priority_conflict(
        self, *, pricing_rule_id: UUID, priority: int, exclude_modifier_id: UUID | None = None
    ) -> bool:
        statement = select(PricingModifier.id).where(
            PricingModifier.pricing_rule_id == pricing_rule_id,
            PricingModifier.priority == priority,
        )
        if exclude_modifier_id is not None:
            statement = statement.where(PricingModifier.id != exclude_modifier_id)
        return self._session.scalar(statement) is not None

    def list_page(
        self, *, pricing_rule_id: UUID | None, page: int, page_size: int
    ) -> tuple[int, list[PricingModifier]]:
        statement = select(PricingModifier)
        count_statement = select(func.count()).select_from(PricingModifier)
        if pricing_rule_id is not None:
            statement = statement.where(PricingModifier.pricing_rule_id == pricing_rule_id)
            count_statement = count_statement.where(PricingModifier.pricing_rule_id == pricing_rule_id)
        total = self._session.scalar(count_statement) or 0
        items = list(
            self._session.exec(
                statement.order_by(PricingModifier.priority, PricingModifier.id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        return total, items

    def list_for_rule(self, rule_id: UUID) -> list[PricingModifier]:
        return list(
            self._session.exec(
                select(PricingModifier)
                .where(PricingModifier.pricing_rule_id == rule_id)
                .order_by(PricingModifier.priority)
            )
        )

    def soft_delete_for_model(self, model_id: UUID) -> None:
        from app.modules.pricing.model.pricing import PricingRule

        self._session.execute(
            update(PricingModifier)
            .where(
                PricingModifier.pricing_rule_id.in_(select(PricingRule.id).where(PricingRule.model_id == model_id)),
                PricingModifier.is_del.is_(False),
            )
            .values(is_del=True)
        )

    def soft_delete_for_rule(self, rule_id: UUID) -> None:
        self._session.execute(
            update(PricingModifier)
            .where(PricingModifier.pricing_rule_id == rule_id, PricingModifier.is_del.is_(False))
            .values(is_del=True)
        )
