from uuid import UUID

from sqlalchemy import update
from sqlmodel import Session, select

from app.modules.pricing.model.pricing_item import PricingItem


class PricingItemCrud:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add_many(self, items: list[PricingItem]) -> None:
        self._session.add_all(items)

    def flush(self) -> None:
        self._session.flush()

    def list_for_rule(self, rule_id: UUID) -> list[PricingItem]:
        return list(
            self._session.exec(
                select(PricingItem).where(PricingItem.pricing_rule_id == rule_id).order_by(PricingItem.position)
            )
        )

    def list_for_rules(self, rule_ids: list[UUID]) -> list[PricingItem]:
        if not rule_ids:
            return []
        return list(
            self._session.exec(
                select(PricingItem)
                .where(PricingItem.pricing_rule_id.in_(rule_ids))
                .order_by(PricingItem.pricing_rule_id, PricingItem.position)
            )
        )

    def sync_for_rule(self, rule_id: UUID, items: list[PricingItem]) -> None:
        """按主键协调方案计费项：保留仍存在的项、逻辑删除被移除的项并新增传入项。"""

        existing = self.list_for_rule(rule_id)
        existing_ids = {item.id for item in existing}
        incoming_ids = {item.id for item in items}
        for item in existing:
            if item.id not in incoming_ids:
                item.is_del = True
        self.add_many([item for item in items if item.id not in existing_ids])

    def soft_delete_for_rule(self, rule_id: UUID) -> None:
        self._session.execute(
            update(PricingItem)
            .where(PricingItem.pricing_rule_id == rule_id, PricingItem.is_del.is_(False))
            .values(is_del=True)
        )

    def soft_delete_for_model(self, model_id: UUID) -> None:
        from app.modules.pricing.model.pricing import PricingRule

        self._session.execute(
            update(PricingItem)
            .where(
                PricingItem.pricing_rule_id.in_(select(PricingRule.id).where(PricingRule.model_id == model_id)),
                PricingItem.is_del.is_(False),
            )
            .values(is_del=True)
        )
