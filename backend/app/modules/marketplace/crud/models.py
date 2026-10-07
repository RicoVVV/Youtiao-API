from uuid import UUID

from sqlalchemy import exists, func
from sqlmodel import Session, select

from app.modules.channels.model.channel import Channel
from app.modules.models.model import Model, ModelRoute
from app.modules.pricing.model.pricing import PricingModifier, PricingRule
from app.modules.pricing.model.pricing_item import PricingItem
from app.modules.user.model.token_group import TokenGroup


class ModelMarketplaceCrud:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_page(
        self,
        *,
        page: int,
        page_size: int,
        model_type: str | None,
        keyword: str | None,
    ) -> tuple[int, list[Model]]:
        statement = self._visible_models_statement()
        if model_type is not None:
            statement = statement.where(Model.model_type == model_type)
        if keyword is not None:
            pattern = f"%{keyword}%"
            statement = statement.where(Model.name.ilike(pattern))
        total = self._session.scalar(select(func.count()).select_from(statement.subquery())) or 0
        items = list(
            self._session.exec(
                statement.order_by(
                    Model.updated_at.desc(),
                    Model.id.asc(),
                )
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        return total, items

    def get_visible(self, model_id: UUID) -> Model | None:
        return self._session.exec(self._visible_models_statement().where(Model.id == model_id)).first()

    def list_public_groups_by_model_ids(self, model_ids: list[UUID]) -> dict[UUID, list[TokenGroup]]:
        if not model_ids:
            return {}
        statement = (
            select(ModelRoute.model_id, TokenGroup)
            .join(ModelRoute, ModelRoute.token_group_id == TokenGroup.id)
            .join(Channel, Channel.id == ModelRoute.channel_id)
            .where(
                ModelRoute.model_id.in_(model_ids),
                ModelRoute.enabled.is_(True),
                ModelRoute.healthy.is_(True),
                Channel.active.is_(True),
                Channel.healthy.is_(True),
                TokenGroup.visibility == "public",
                TokenGroup.is_active.is_(True),
            )
            .distinct()
            .order_by(ModelRoute.model_id.asc(), TokenGroup.name.asc(), TokenGroup.id.asc())
        )
        groups_by_model_id: dict[UUID, list[TokenGroup]] = {model_id: [] for model_id in model_ids}
        for model_id, group in self._session.exec(statement):
            groups_by_model_id.setdefault(model_id, []).append(group)
        return groups_by_model_id

    def list_active_rules_for_groups(self, *, model_ids: list[UUID], group_ids: list[int]) -> list[PricingRule]:
        """读取指定模型与公开分组下启用中的定价规则，供模型广场展示分档价格。"""

        if not model_ids or not group_ids:
            return []
        return list(
            self._session.exec(
                select(PricingRule)
                .where(
                    PricingRule.model_id.in_(model_ids),
                    PricingRule.token_group_id.in_(group_ids),
                    PricingRule.active.is_(True),
                )
                .order_by(PricingRule.model_id, PricingRule.token_group_id, PricingRule.priority)
            )
        )

    def list_active_items_for_rules(self, rule_ids: list[UUID]) -> list[PricingItem]:
        """读取规则下启用中的计费项，保持 position 顺序。"""

        if not rule_ids:
            return []
        return list(
            self._session.exec(
                select(PricingItem)
                .where(PricingItem.pricing_rule_id.in_(rule_ids), PricingItem.active.is_(True))
                .order_by(PricingItem.pricing_rule_id, PricingItem.position)
            )
        )

    def list_active_modifiers_for_rules(self, rule_ids: list[UUID]) -> list[PricingModifier]:
        if not rule_ids:
            return []
        return list(
            self._session.exec(
                select(PricingModifier)
                .where(PricingModifier.pricing_rule_id.in_(rule_ids), PricingModifier.active.is_(True))
                .order_by(PricingModifier.pricing_rule_id, PricingModifier.priority)
            )
        )

    @staticmethod
    def _visible_models_statement():
        public_route_exists = exists(
            select(ModelRoute.id)
            .join(Channel, Channel.id == ModelRoute.channel_id)
            .join(TokenGroup, TokenGroup.id == ModelRoute.token_group_id)
            .where(
                ModelRoute.model_id == Model.id,
                ModelRoute.enabled.is_(True),
                ModelRoute.healthy.is_(True),
                Channel.active.is_(True),
                Channel.healthy.is_(True),
                TokenGroup.visibility == "public",
                TokenGroup.is_active.is_(True),
            )
        )
        return select(Model).where(Model.active.is_(True), Model.template_id.is_not(None), public_route_exists)
