"""渠道、模型能力和价格配置的数据访问。"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.channels.model.channel import Channel
from app.modules.models.model import Model, ModelRoute
from app.modules.pricing.model.pricing import PricingModifier, PricingRule
from app.modules.pricing.model.pricing_item import PricingItem


class ChannelCrud:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_active_model(self, *, name: str, model_type: str) -> Model | None:
        return self._session.scalar(
            select(Model).where(Model.name == name, Model.model_type == model_type, Model.active.is_(True))
        )

    def get_active_model_type(self, *, name: str) -> str | None:
        """读取启用模型的类型，供原生协议按模型能力分流。"""

        return self._session.scalar(select(Model.model_type).where(Model.name == name, Model.active.is_(True)))

    def list_active_models_for_groups(self, *, group_ids: list[int]) -> list[Model]:
        """列出指定分组下存在启用且健康路由的启用模型。"""

        if not group_ids:
            return []
        return list(
            self._session.scalars(
                select(Model)
                .join(ModelRoute, ModelRoute.model_id == Model.id)
                .join(Channel, Channel.id == ModelRoute.channel_id)
                .where(
                    Model.active.is_(True),
                    ModelRoute.token_group_id.in_(group_ids),
                    ModelRoute.enabled.is_(True),
                    ModelRoute.healthy.is_(True),
                    Channel.active.is_(True),
                    Channel.healthy.is_(True),
                )
                .distinct()
                .order_by(Model.name.asc())
            )
        )

    def list_channels_for_model(self, *, model_id: UUID, group_ids: list[int]) -> list[tuple[ModelRoute, Channel]]:
        if not group_ids:
            return []
        rows = self._session.execute(
            select(ModelRoute, Channel)
            .join(Channel, Channel.id == ModelRoute.channel_id)
            .where(ModelRoute.model_id == model_id, ModelRoute.token_group_id.in_(group_ids))
        )
        return list(rows)

    def get_channel_by_id(self, *, channel_id: UUID) -> Channel | None:
        channel = self._session.get(Channel, channel_id)
        if channel is not None:
            return channel
        return self._session.scalar(
            select(Channel).where(Channel.id == channel_id).execution_options(include_deleted=True)
        )

    def get_model_route_by_id(self, *, route_id: UUID) -> ModelRoute | None:
        route = self._session.get(ModelRoute, route_id)
        if route is not None:
            return route
        return self._session.scalar(
            select(ModelRoute).where(ModelRoute.id == route_id).execution_options(include_deleted=True)
        )

    def list_pricing_configuration(
        self, *, model_id: UUID
    ) -> tuple[list[PricingRule], list[PricingItem], list[PricingModifier]]:
        rules = list(self._session.scalars(select(PricingRule).where(PricingRule.model_id == model_id)))
        if not rules:
            return rules, [], []
        rule_ids = [rule.id for rule in rules]
        items = list(self._session.scalars(select(PricingItem).where(PricingItem.pricing_rule_id.in_(rule_ids))))
        modifiers = list(
            self._session.scalars(select(PricingModifier).where(PricingModifier.pricing_rule_id.in_(rule_ids)))
        )
        return rules, items, modifiers
