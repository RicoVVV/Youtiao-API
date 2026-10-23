"""渠道、模型能力和价格配置的数据访问。"""

from uuid import UUID

from sqlalchemy import or_, select
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

    def list_group_model_types(self, *, group_ids: list[int]) -> dict[int, list[str]]:
        """按分组列出当前配置支持的模型类型。

        只按启用模型、启用路由与启用渠道判断，不看健康状态：渠道暂时不健康时
        分组仍应出现在监控页，否则故障会被隐藏。
        """

        if not group_ids:
            return {}
        rows = self._session.execute(
            select(ModelRoute.token_group_id, Model.model_type)
            .join(Model, Model.id == ModelRoute.model_id)
            .join(Channel, Channel.id == ModelRoute.channel_id)
            .where(
                ModelRoute.token_group_id.in_(group_ids),
                ModelRoute.enabled.is_(True),
                Model.active.is_(True),
                Channel.active.is_(True),
            )
            .distinct()
        ).all()
        types_by_group: dict[int, set[str]] = {}
        for group_id, model_type in rows:
            if isinstance(model_type, str):
                types_by_group.setdefault(int(group_id), set()).add(model_type)
        return {group_id: sorted(types) for group_id, types in types_by_group.items()}

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

    def get_channel_for_update(self, *, channel_id: UUID) -> Channel | None:
        """加锁读取渠道，供自动停用与自动启用避免与管理员操作互相覆盖。"""

        return self._session.scalar(select(Channel).where(Channel.id == channel_id).with_for_update())

    def get_model_route_by_id(self, *, route_id: UUID) -> ModelRoute | None:
        route = self._session.get(ModelRoute, route_id)
        if route is not None:
            return route
        return self._session.scalar(
            select(ModelRoute).where(ModelRoute.id == route_id).execution_options(include_deleted=True)
        )

    def list_routes_for_channel(self, *, channel_id: UUID) -> list[ModelRoute]:
        """列出渠道当前有效的全部模型路由，用于运行时状态重置与详情展示。"""

        return list(self._session.scalars(select(ModelRoute).where(ModelRoute.channel_id == channel_id)))

    def list_channels_with_routes(self) -> list[tuple[Channel, ModelRoute]]:
        """一次性读取全部渠道与其路由，供趋势采样聚合使用。"""

        return list(
            self._session.execute(
                select(Channel, ModelRoute)
                .join(ModelRoute, ModelRoute.channel_id == Channel.id)
                .order_by(Channel.id, ModelRoute.id)
            ).all()
        )

    def list_probe_channels(self) -> list[Channel]:
        """列出需要健康探测的渠道：启用渠道与因探测自动停用的渠道。"""

        return list(
            self._session.scalars(
                select(Channel).where(or_(Channel.active.is_(True), Channel.auto_disabled_at.is_not(None)))
            )
        )

    def list_active_models_by_names(self, *, names: list[str]) -> list[Model]:
        """按模型名批量读取启用模型，供探测选择最小文本请求目标。"""

        if not names:
            return []
        return list(self._session.scalars(select(Model).where(Model.name.in_(names), Model.active.is_(True))))

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
