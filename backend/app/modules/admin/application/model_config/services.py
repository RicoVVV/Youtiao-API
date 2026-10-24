"""管理员模型、渠道和能力配置应用服务。"""

import logging
from collections.abc import Callable, Iterable
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.bootstrap.container import get_model_catalog, get_provider_template_registry
from app.core.config import get_settings
from app.core.errors import NotFoundError, ValidationError, error_context
from app.core.i18n import get_locale
from app.modules.admin.crud.channel_crud import ChannelCrud
from app.modules.admin.crud.model_capability_crud import ModelRouteCrud
from app.modules.admin.crud.model_crud import ModelCrud
from app.modules.admin.crud.pricing_item_crud import PricingItemCrud
from app.modules.admin.crud.pricing_modifier_crud import PricingModifierCrud
from app.modules.admin.crud.pricing_rule_crud import PricingRuleCrud
from app.modules.channels.application.validation import validate_configuration
from app.modules.channels.crud.channels import ChannelCrud as ConfigurationChannelCrud
from app.modules.channels.crud.samples import ChannelRuntimeSampleCrud
from app.modules.channels.model.channel import Channel
from app.modules.channels.runtime.channel_runtime import get_channel_runtime
from app.modules.channels.runtime.routing_snapshot import publish_routing_snapshot_invalidation
from app.modules.model_catalog.entries import ModelPricingEntry
from app.modules.model_catalog.matching import infer_model_type
from app.modules.model_catalog.registry import CatalogMatch
from app.modules.models.model import Model, ModelRoute
from app.modules.pricing.model.pricing import PricingModifier, PricingRule
from app.modules.pricing.model.pricing_item import PricingItem, PricingItemKind
from app.modules.user.crud.token_group_crud import TokenGroupCrud
from app.modules.user.model.token_group import TokenGroup

logger = logging.getLogger(__name__)

_TEXT_INPUT_ITEM_KINDS = (
    PricingItemKind.input_text_tokens.value,
    PricingItemKind.cache_write_input_text_tokens.value,
    PricingItemKind.cached_input_text_tokens.value,
)
_TEXT_OUTPUT_ITEM_KINDS = (PricingItemKind.output_text_tokens.value,)


class AdminModelConfigApplicationService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def _write(self, action):
        try:
            result = action()
            self._session.commit()
            publish_routing_snapshot_invalidation()
            return result
        except IntegrityError as exc:
            self._session.rollback()
            raise _integrity_error_to_validation_error(exc) from exc
        except ValidationError:
            self._session.rollback()
            raise
        except ValueError as exc:
            self._session.rollback()
            raise ValidationError(str(exc), **error_context(exc)) from exc
        except Exception:
            self._session.rollback()
            raise

    def create_channel(self, payload: dict[str, Any]) -> dict[str, object]:
        return self._write(lambda: create_channel(self._session, **payload))

    def update_channel(self, payload: dict[str, Any]) -> dict[str, object]:
        data = payload.copy()
        return self._write(lambda: update_channel(self._session, channel_id=data.pop("channel_id"), **data))

    def update_channel_status(self, payload: dict[str, Any]) -> dict[str, object]:
        return self._write(lambda: update_channel_status(self._session, **payload))

    def delete_channel(self, payload: dict[str, Any]) -> None:
        self._write(lambda: delete_channel(self._session, **payload))

    def list_channels(
        self,
        *,
        channel_name: str | None,
        model_name: str | None,
        token_group_name: str | None,
        page: int,
        page_size: int,
    ) -> tuple[int, list[dict[str, object]]]:
        total, items = ChannelCrud(self._session).list_page(
            channel_name=channel_name,
            model_name=model_name,
            token_group_name=token_group_name,
            page=page,
            page_size=page_size,
        )
        group_ids = {group_id for item in items for group_id in item.token_group_ids}
        groups_by_id = {
            group.id: group
            for group in TokenGroupCrud(self._session).list_groups_by_ids(group_ids)
            if group.id is not None
        }
        return total, [_channel_view(item, groups_by_id=groups_by_id) for item in items]

    def get_channel(self, channel_id: UUID) -> dict[str, object]:
        channel = ChannelCrud(self._session).get(channel_id)
        if channel is None:
            raise NotFoundError("视频渠道不存在")
        view = _channel_view(channel)
        view["runtime"] = _channel_runtime_view(self._session, channel)
        return view

    def get_channel_trend(self, *, channel_id: UUID, hours: int) -> dict[str, object]:
        """读取渠道最近若干小时的运行时趋势采样。"""

        channel = ChannelCrud(self._session).get(channel_id)
        if channel is None:
            raise NotFoundError("视频渠道不存在")
        settings = get_settings()
        if hours > settings.routing_trend_max_hours:
            raise ValidationError(
                f"趋势查询时长不能超过 {settings.routing_trend_max_hours} 小时",
                code="channel.trend_hours_exceeded",
                params={"hours": settings.routing_trend_max_hours},
            )
        end_at = datetime.now(UTC)
        rows = ChannelRuntimeSampleCrud(self._session).list_range(
            channel_id=channel_id,
            start_at=end_at - timedelta(hours=hours),
            end_at=end_at,
        )
        return {
            "channel_id": str(channel_id),
            "bucket_seconds": 60,
            "start": (end_at - timedelta(hours=hours)).isoformat(),
            "end": end_at.isoformat(),
            "points": [
                {
                    "bucket_start": row.bucket_start.isoformat(),
                    "effective_weight": float(row.effective_weight),
                    "success_rate": float(row.success_rate) if row.success_rate is not None else None,
                    "average_latency_ms": row.average_latency_ms,
                    "circuit_state": row.circuit_state,
                    "active": row.active,
                }
                for row in rows
            ],
        }

    def copy_channel(self, payload: dict[str, Any]) -> dict[str, object]:
        return self._write(lambda: self._copy_channel(payload["channel_id"]))

    def _copy_channel(self, channel_id: UUID) -> dict[str, object]:
        """把渠道连同其供应商连接配置复制为一份新渠道，不改动任何模型。"""

        channel_crud = ChannelCrud(self._session)
        source = channel_crud.get(channel_id)
        if source is None:
            raise NotFoundError("视频渠道不存在")
        channel = Channel(
            name=_copy_name(source.name, exists=channel_crud.exists_name, max_length=128),
            base_url=source.base_url,
            api_key=source.api_key,
            config=deepcopy(source.config),
            supported_models=list(source.supported_models),
            token_group_ids=list(source.token_group_ids),
            model_mapping=deepcopy(source.model_mapping),
            param_override=deepcopy(source.param_override),
            header_override=deepcopy(source.header_override),
            priority=source.priority,
            weight=source.weight,
            active=source.active,
            healthy=source.healthy,
        )
        _validate_channel(channel)
        channel_crud.add(channel)
        channel_crud.flush()
        _sync_channel_routes(self._session, channel)
        return {"id": str(channel.id), "name": channel.name}

    def create_model(self, payload: dict[str, Any]) -> dict[str, object]:
        return self._write(lambda: create_model(self._session, **payload))

    def match_model_preview(
        self, *, name: str, provider_id: str | None = None, model_type: str | None = None
    ) -> dict[str, object]:
        """预览按模型名自动匹配的结果，供管理员在创建前确认模板与价格。

        指定 ``provider_id`` 时只在该 Provider 的预设模型价格内匹配；未命中时返回该 Provider 默认模板的
        定价骨架，并标记 ``requires_pricing_input`` 要求管理员补填单价。``model_type`` 用于在 Provider
        内显式指定模板能力，未提供时按模型名推断。
        """

        try:
            return _match_preview(get_model_catalog().match(name), provider_id=provider_id, model_type=model_type)
        except ValidationError:
            raise
        except ValueError as exc:
            raise ValidationError(str(exc), **error_context(exc)) from exc

    def list_model_providers(self) -> dict[str, object]:
        """返回创建模型时可选的 Provider 及其支持的模型类型。"""

        return {"items": _provider_summaries()}

    def batch_match_model_preview(
        self, *, model_names: list[str], provider_id: str | None = None, model_type: str | None = None
    ) -> dict[str, object]:
        """批量预览所选模型的模板与预设定价。

        每个模型独立返回结果：预设命中、需要手动填写价格或解析失败，供前端渲染批量配置表格。
        重复名称只保留首次出现，空名称会被忽略。
        """

        items: list[dict[str, Any]] = []
        seen: set[str] = set()
        preset_matched = 0
        requires_pricing_input = 0
        failed = 0
        for raw_name in model_names:
            name = raw_name.strip()
            if not name or name in seen:
                continue
            seen.add(name)
            item = _batch_preview_item(name, provider_id=provider_id, model_type=model_type)
            items.append(item)
            if item["error"] is not None:
                failed += 1
            elif item["matched"]:
                preset_matched += 1
            if item["requires_pricing_input"]:
                requires_pricing_input += 1
        return {
            "items": items,
            "summary": {
                "total": len(items),
                "preset_matched": preset_matched,
                "requires_pricing_input": requires_pricing_input,
                "failed": failed,
            },
        }

    def batch_create_models(self, payload: dict[str, Any]) -> dict[str, object]:
        """批量创建模型；任一模型失败时整体回滚，不做部分创建。

        可按 ``token_group_ids`` 为整批模型指定默认定价规则的播种分组，未指定时回退到系统默认分组。
        每个模型可覆盖公共的 ``provider_id``、``template_id``、``model_type`` 与 ``pricing_rules``。
        """

        items = payload["items"]
        common_provider_id = payload.get("provider_id")
        token_group_ids = payload.get("token_group_ids")
        names = [str(item["name"]).strip() for item in items]
        if any(not name for name in names):
            raise ValidationError("模型名不能为空")
        if len(names) != len(set(names)):
            raise ValidationError("批量创建的模型名不能重复")

        def action() -> dict[str, object]:
            results: list[dict[str, object]] = []
            for item, name in zip(items, names, strict=True):
                try:
                    results.append(
                        create_model(
                            self._session,
                            name=name,
                            description=item.get("description"),
                            template_id=item.get("template_id"),
                            provider_id=item.get("provider_id") or common_provider_id,
                            model_type=item.get("model_type"),
                            pricing_rules=item.get("pricing_rules"),
                            token_group_ids=token_group_ids,
                            default_concurrency_limit=item.get("default_concurrency_limit"),
                            active=item.get("active", True),
                        )
                    )
                except ValidationError as exc:
                    raise ValidationError(f"模型“{name}”创建失败：{exc}") from exc
            return {"items": results}

        return self._write(action)

    def update_model(self, payload: dict[str, Any]) -> dict[str, object]:
        data = payload.copy()
        return self._write(lambda: update_model(self._session, model_id=data.pop("model_id"), **data))

    def update_model_status(self, payload: dict[str, Any]) -> dict[str, object]:
        return self._write(lambda: update_model_status(self._session, **payload))

    def delete_model(self, payload: dict[str, Any]) -> None:
        self._write(lambda: delete_model(self._session, **payload))

    def list_models(
        self, *, model_name: str | None, provider_id: str | None, page: int, page_size: int
    ) -> tuple[int, list[dict[str, object]]]:
        providers = _provider_identities()
        template_ids = (
            [template_id for template_id, provider in providers.items() if provider[0] == provider_id]
            if provider_id
            else None
        )
        total, items = ModelCrud(self._session).list_page(
            model_name=model_name, template_ids=template_ids, page=page, page_size=page_size
        )
        return total, [_model_view(item, providers=providers) for item in items]

    def get_model(self, model_id: UUID) -> dict[str, object]:
        return _model_view(_get_live_model(self._session, model_id), providers=_provider_identities())

    def copy_model(self, payload: dict[str, Any]) -> dict[str, object]:
        return self._write(lambda: self._copy_model(payload["model_id"]))

    def _copy_model(self, model_id: UUID) -> dict[str, object]:
        """复制模型本体与其全部计费方案，并让副本继承源模型的渠道绑定。"""

        source = _get_live_model(self._session, model_id)
        model_crud = ModelCrud(self._session)
        model = Model(
            name=_copy_name(source.name, exists=lambda name: model_crud.get_by_name(name) is not None, max_length=64),
            description=source.description,
            model_type=source.model_type,
            template_id=source.template_id,
            input_contract=deepcopy(source.input_contract),
            pricing_fields=list(source.pricing_fields),
            default_concurrency_limit=source.default_concurrency_limit,
            active=source.active,
        )
        model_crud.add(model)
        model_crud.flush()
        self._clone_pricing_rules(source_model_id=source.id, target_model_id=model.id)
        self._bind_model_to_referencing_channels(source_name=source.name, new_model_name=model.name)
        return {"id": str(model.id), "name": model.name}

    def _bind_model_to_referencing_channels(self, *, source_name: str, new_model_name: str) -> None:
        """把新模型名加入引用源模型的渠道并重建路由，使副本可路由、可见于模型广场。"""

        channel_crud = ChannelCrud(self._session)
        for channel in channel_crud.list_referencing_model(source_name):
            if new_model_name not in channel.supported_models:
                channel.supported_models = [*channel.supported_models, new_model_name]
            if source_name in channel.model_mapping:
                channel.model_mapping = {
                    **channel.model_mapping,
                    new_model_name: deepcopy(channel.model_mapping[source_name]),
                }
            _validate_channel(channel)
            _sync_channel_routes(self._session, channel)

    def _clone_pricing_rules(self, *, source_model_id: UUID, target_model_id: UUID) -> None:
        """把源模型下的计费方案整份复制到目标模型，保留原令牌组与优先级。"""

        rule_crud = PricingRuleCrud(self._session)
        for source_rule in rule_crud.list_for_model(source_model_id):
            rule = PricingRule(
                model_id=target_model_id,
                token_group_id=source_rule.token_group_id,
                name=source_rule.name,
                priority=source_rule.priority,
                conditions=deepcopy(source_rule.conditions),
                currency=source_rule.currency,
                active=source_rule.active,
            )
            rule_crud.add(rule)
            rule_crud.flush()
            self._clone_rule_children(source_rule_id=source_rule.id, target_rule_id=rule.id)

    def _clone_rule_children(self, *, source_rule_id: UUID, target_rule_id: UUID) -> None:
        """复制方案内的计费项与修正项，并把计费项之间的主键引用重映射到副本。"""

        item_crud = PricingItemCrud(self._session)
        source_items = item_crud.list_for_rule(source_rule_id)
        item_id_map: dict[str, str] = {}
        items: list[PricingItem] = []
        for source_item in source_items:
            item = PricingItem(
                pricing_rule_id=target_rule_id,
                label=source_item.label,
                position=source_item.position,
                kind=source_item.kind,
                source_fields=list(source_item.source_fields),
                estimate_config=deepcopy(source_item.estimate_config),
                free_quantity=source_item.free_quantity,
                unit_amount=source_item.unit_amount,
                active=source_item.active,
            )
            item_id_map[str(source_item.id)] = str(item.id)
            items.append(item)
        for source_item, item in zip(source_items, items, strict=True):
            if source_item.price_source_item_id is not None:
                item.price_source_item_id = UUID(item_id_map[str(source_item.price_source_item_id)])
        item_crud.add_many(items)
        modifier_crud = PricingModifierCrud(self._session)
        for source_modifier in modifier_crud.list_for_rule(source_rule_id):
            modifier_crud.add(
                PricingModifier(
                    pricing_rule_id=target_rule_id,
                    name=source_modifier.name,
                    priority=source_modifier.priority,
                    conditions=deepcopy(source_modifier.conditions),
                    effect_type=source_modifier.effect_type,
                    effect_payload=deepcopy(source_modifier.effect_payload),
                    scope_type=source_modifier.scope_type,
                    scope_item_ids=[item_id_map.get(item_id, item_id) for item_id in source_modifier.scope_item_ids],
                    scope_item_kinds=list(source_modifier.scope_item_kinds),
                    active=source_modifier.active,
                )
            )

    def create_pricing_rule(self, payload: dict[str, Any]) -> dict[str, object]:
        return self._write(lambda: create_pricing_rule(self._session, **payload))

    def update_pricing_rule(self, payload: dict[str, Any]) -> dict[str, object]:
        data = payload.copy()
        return self._write(lambda: update_pricing_rule(self._session, rule_id=data.pop("pricing_rule_id"), **data))

    def delete_pricing_rule(self, payload: dict[str, Any]) -> None:
        self._write(lambda: delete_pricing_rule(self._session, rule_id=payload["pricing_rule_id"]))

    def list_pricing_rules(
        self, *, model_id: UUID | None, keyword: str | None, page: int, page_size: int
    ) -> tuple[int, list[dict[str, object]]]:
        total, items = PricingRuleCrud(self._session).list_page(
            model_id=model_id, keyword=keyword, page=page, page_size=page_size
        )
        items_by_rule = _items_by_rule(PricingItemCrud(self._session).list_for_rules([item.id for item in items]))
        return total, [_pricing_rule_view(item, items=items_by_rule.get(item.id, [])) for item in items]

    def get_pricing_rule(self, pricing_rule_id: UUID) -> dict[str, object]:
        rule = PricingRuleCrud(self._session).get(pricing_rule_id)
        if rule is None:
            raise NotFoundError("价格规则不存在")
        return _pricing_rule_view(rule, items=PricingItemCrud(self._session).list_for_rule(rule.id))

    def copy_pricing_rule(self, payload: dict[str, Any]) -> dict[str, object]:
        return self._write(lambda: self._copy_pricing_rule(payload["pricing_rule_id"]))

    def _copy_pricing_rule(self, pricing_rule_id: UUID) -> dict[str, object]:
        """在同一模型与令牌组内复制计费方案，并自动取用未被占用的优先级。"""

        rule_crud = PricingRuleCrud(self._session)
        source = rule_crud.get_for_update(pricing_rule_id)
        if source is None:
            raise NotFoundError("价格规则不存在")
        # 与新建规则保持一致的加锁顺序：先锁来源规则，再锁模型，串行化同模型内的优先级分配。
        ModelCrud(self._session).get_for_update(source.model_id)
        rule = PricingRule(
            model_id=source.model_id,
            token_group_id=source.token_group_id,
            name=_copy_name(
                source.name,
                exists=lambda name: rule_crud.exists_name(
                    model_id=source.model_id, token_group_id=source.token_group_id, name=name
                ),
                max_length=128,
            ),
            priority=_next_priority_in_scope(
                rule_crud.list_in_scope(model_id=source.model_id, token_group_id=source.token_group_id),
                conditional=bool(source.conditions),
            ),
            conditions=deepcopy(source.conditions),
            currency=source.currency,
            active=source.active,
        )
        rule_crud.add(rule)
        rule_crud.flush()
        self._clone_rule_children(source_rule_id=source.id, target_rule_id=rule.id)
        return {"id": str(rule.id), "name": rule.name, "priority": rule.priority}

    def create_pricing_modifier(self, payload: dict[str, Any]) -> dict[str, object]:
        return self._write(lambda: create_pricing_modifier(self._session, **payload))

    def update_pricing_modifier(self, payload: dict[str, Any]) -> dict[str, object]:
        data = payload.copy()
        return self._write(
            lambda: update_pricing_modifier(self._session, modifier_id=data.pop("pricing_modifier_id"), **data)
        )

    def delete_pricing_modifier(self, payload: dict[str, Any]) -> None:
        self._write(lambda: delete_pricing_modifier(self._session, modifier_id=payload["pricing_modifier_id"]))

    def list_pricing_modifiers(
        self, *, pricing_rule_id: UUID | None, page: int, page_size: int
    ) -> tuple[int, list[dict[str, object]]]:
        total, items = PricingModifierCrud(self._session).list_page(
            pricing_rule_id=pricing_rule_id, page=page, page_size=page_size
        )
        return total, [_pricing_modifier_view(item) for item in items]

    def get_pricing_modifier(self, pricing_modifier_id: UUID) -> dict[str, object]:
        modifier = PricingModifierCrud(self._session).get(pricing_modifier_id)
        if modifier is None:
            raise NotFoundError("价格修正不存在")
        return _pricing_modifier_view(modifier)

    def copy_pricing_modifier(self, payload: dict[str, Any]) -> dict[str, object]:
        return self._write(lambda: self._copy_pricing_modifier(payload["pricing_modifier_id"]))

    def _copy_pricing_modifier(self, pricing_modifier_id: UUID) -> dict[str, object]:
        """在同一计费方案内复制修正项，并自动取用未被占用的优先级。"""

        modifier_crud = PricingModifierCrud(self._session)
        source = modifier_crud.get_for_update(pricing_modifier_id)
        if source is None:
            raise NotFoundError("价格修正不存在")
        PricingRuleCrud(self._session).get_for_update(source.pricing_rule_id)
        modifier = PricingModifier(
            pricing_rule_id=source.pricing_rule_id,
            name=_copy_name(
                source.name,
                exists=lambda name: modifier_crud.exists_name(pricing_rule_id=source.pricing_rule_id, name=name),
                max_length=128,
            ),
            priority=_next_priority_in_scope(
                modifier_crud.list_for_rule(source.pricing_rule_id),
                conditional=bool(source.conditions),
            ),
            conditions=deepcopy(source.conditions),
            effect_type=source.effect_type,
            effect_payload=deepcopy(source.effect_payload),
            scope_type=source.scope_type,
            scope_item_ids=list(source.scope_item_ids),
            scope_item_kinds=list(source.scope_item_kinds),
            active=source.active,
        )
        modifier_crud.add(modifier)
        modifier_crud.flush()
        return {"id": str(modifier.id), "name": modifier.name, "priority": modifier.priority}


def _integrity_error_to_validation_error(exc: IntegrityError) -> ValidationError:
    diagnostic = getattr(getattr(exc, "orig", None), "diag", None)
    constraint_name = getattr(diagnostic, "constraint_name", None)
    database_error = getattr(exc, "orig", None) or exc
    messages = {
        "uq_models_name_active": "模型名称已存在",
        "uq_model_routes_model_group_channel_active": "模型渠道绑定已存在",
        "uq_pricing_rules_model_group_priority_active": "同一模型和令牌组内价格规则 priority 不能重复",
        "uq_pricing_modifiers_rule_priority_active": "同一价格规则内价格修正规则 priority 不能重复",
        "uq_pricing_items_rule_position_active": "同一计费方案内计费项 position 不能重复",
    }
    if constraint_name not in messages:
        # 未收录的约束（外键、非空、检查约束）无法给出面向用户的文案，必须在日志留全量现场，
        # 否则这类缺陷只会表现为无迹可查的「数据完整性校验失败」。
        logger.warning(
            "未映射的数据库完整性约束冲突",
            extra={"constraint_name": constraint_name, "database_error": str(database_error)},
        )
    return ValidationError(messages.get(constraint_name, "数据完整性校验失败"))


def _copy_name(base: str, *, exists: Callable[[str], bool], max_length: int) -> str:
    """生成副本名称：追加 ``_copy``，重名时递增编号，并按字段上限截断原名。"""

    suffix = "_copy"
    index = 1
    while True:
        current = suffix if index == 1 else f"{suffix}_{index}"
        candidate = f"{base[: max_length - len(current)]}{current}"
        if not exists(candidate):
            return candidate
        index += 1


def _get_live_model(session: Session, model_id: UUID) -> Model:
    """读取未被逻辑删除的模型，命中已删除记录时给出明确提示。"""

    crud = ModelCrud(session)
    model = crud.get(model_id)
    if model is not None:
        return model
    raise _model_not_found(crud=crud, model_id=model_id)


def _get_live_model_for_update(session: Session, model_id: UUID) -> Model:
    """加锁读取未被逻辑删除的模型，命中已删除记录时给出明确提示。"""

    crud = ModelCrud(session)
    model = crud.get_for_update(model_id)
    if model is not None:
        return model
    raise _model_not_found(crud=crud, model_id=model_id)


def _model_not_found(*, crud: ModelCrud, model_id: UUID) -> NotFoundError:
    """区分逻辑删除与从未存在，避免把已删除模型笼统报成不存在。"""

    return NotFoundError("模型已删除" if crud.get_including_deleted(model_id) is not None else "模型不存在")


def create_channel(session: Session, **payload: Any) -> dict[str, object]:
    channel = Channel(**payload)
    _validate_channel(channel)
    channel_crud = ChannelCrud(session)
    channel_crud.add(channel)
    channel_crud.flush()
    _sync_channel_routes(session, channel)
    return {"id": str(channel.id)}


def update_channel(session: Session, *, channel_id: UUID, **payload: Any) -> dict[str, object]:
    api_key = payload.pop("api_key")
    channel = ChannelCrud(session).get_for_update(channel_id)
    if channel is None:
        raise NotFoundError("视频渠道不存在")
    reset_runtime = False
    for key, value in payload.items():
        if key in {"weight", "priority"} and getattr(channel, key) != value:
            reset_runtime = True
        setattr(channel, key, value)
    if api_key is not None:
        channel.api_key = api_key
    if channel.active:
        channel.auto_disabled_at = None
    _validate_channel(channel)
    _sync_channel_routes(session, channel)
    if reset_runtime:
        _reset_channel_route_runtime(session, channel_id)
    return {"id": str(channel.id)}


def update_channel_status(session: Session, *, channel_id: UUID, active: bool) -> dict[str, object]:
    channel = ChannelCrud(session).get_for_update(channel_id)
    if channel is None:
        raise NotFoundError("视频渠道不存在")
    channel.active = active
    if active:
        channel.auto_disabled_at = None
    _sync_channel_routes(session, channel)
    return {"id": str(channel.id), "active": channel.active}


def delete_channel(session: Session, *, channel_id: UUID) -> None:
    channel_crud = ChannelCrud(session)
    channel = channel_crud.get_for_update(channel_id)
    if channel is None:
        raise NotFoundError("视频渠道不存在")
    channel.is_del = True
    channel_crud.soft_delete_bindings(channel.id)


def create_model(session: Session, **payload: Any) -> dict[str, object]:
    token_group_ids = payload.pop("token_group_ids", None)
    manual_rules = payload.pop("pricing_rules", None)
    provider_id = payload.pop("provider_id", None)
    match = get_model_catalog().match(payload["name"])
    template_id, model_type, preset_entry = _resolve_model_template(payload, match=match, provider_id=provider_id)
    payload["template_id"] = template_id
    payload["model_type"] = model_type
    payload["input_contract"] = _build_input_contract(template_id, model_type, payload.get("input_contract"))
    payload["pricing_fields"] = list(payload.get("pricing_fields") or [])
    model = Model(**payload)
    if ModelCrud(session).get_by_name(model.name) is not None:
        raise ValidationError("模型名称已存在")
    default_rules = _resolve_default_pricing_rules(
        match=match,
        template_id=template_id,
        preset_entry=preset_entry,
        manual_rules=manual_rules,
        provider_id=provider_id,
    )
    model.pricing_fields = _merge_pricing_fields(model.input_contract, model.pricing_fields, default_rules)
    _validate_model(model)
    validate_configuration(
        channels=[],
        rules=[],
        modifiers=[],
        allowed_fields=model.pricing_fields,
        input_schema=_input_schema(model),
        standardized_projection=_projection(model),
        material_fields=_material_fields(model),
        derived_pricing_fields=_derived_pricing_fields(model),
        model_type=model.model_type,
    )
    model_crud = ModelCrud(session)
    model_crud.add(model)
    model_crud.flush()
    _seed_default_pricing_rules(
        session,
        model=model,
        rules=default_rules,
        modifiers=_long_context_modifiers(preset_entry),
        group_ids=token_group_ids,
    )
    return {"id": str(model.id), "name": model.name, "pricing_configured": _pricing_configured(default_rules)}


def _resolve_default_pricing_rules(
    *,
    match: CatalogMatch,
    template_id: str,
    preset_entry: ModelPricingEntry | None,
    manual_rules: list[dict[str, Any]] | None,
    provider_id: str | None,
) -> list[dict[str, Any]]:
    """解析新建模型要播种的定价规则。

    手动规则优先；其次使用 Provider 预设的目录价格；指定 Provider 但未命中预设时拒绝创建，
    要求管理员先填写价格。未指定 Provider 时保留按模板兜底价格播种的既有行为。
    """

    if manual_rules is not None:
        rules = _normalize_manual_pricing_rules(manual_rules)
        if not _pricing_configured(rules):
            raise ValidationError("请填写完整的计费项单价")
        return rules
    if preset_entry is not None:
        return _catalog_pricing_rules(match, _template_pricing_rules(template_id))
    if provider_id is not None:
        raise ValidationError("该模型未匹配到所选 Provider 的预设价格，请手动填写定价规则")
    return _template_pricing_rules(template_id)


_MANUAL_PRICING_ITEM_FIELDS = (
    "label",
    "position",
    "kind",
    "source_fields",
    "estimate_config",
    "free_quantity",
    "unit_amount",
    "active",
)


def _normalize_manual_pricing_rules(rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """把管理员提交的定价规则裁剪为落库允许的字段，避免请求中的展示字段进入 ORM 构造。"""

    normalized: list[dict[str, Any]] = []
    for rule in rules:
        name = rule.get("name")
        items = rule.get("items")
        conditions = rule.get("conditions") or []
        if not isinstance(name, str) or not name or not isinstance(items, list) or not items:
            raise ValidationError("定价规则不合法")
        if not isinstance(conditions, list) or any(not isinstance(condition, dict) for condition in conditions):
            raise ValidationError("定价规则不合法")
        normalized_items = [
            {key: deepcopy(item[key]) for key in _MANUAL_PRICING_ITEM_FIELDS if key in item}
            for item in items
            if isinstance(item, dict)
        ]
        if len(normalized_items) != len(items) or any(
            not isinstance(item.get("label"), str)
            or not isinstance(item.get("position"), int)
            or not isinstance(item.get("kind"), str)
            for item in normalized_items
        ):
            raise ValidationError("定价规则不合法")
        normalized_rule: dict[str, Any] = {
            "name": name,
            "conditions": deepcopy(conditions),
            "items": normalized_items,
        }
        currency = rule.get("currency")
        if isinstance(currency, str) and currency:
            normalized_rule["currency"] = currency
        normalized.append(normalized_rule)
    return normalized


def _resolve_model_template(
    payload: dict[str, Any], *, match: CatalogMatch, provider_id: str | None
) -> tuple[str, str, ModelPricingEntry | None]:
    """解析新建模型使用的模板、模型类型与可播种的预设价格条目。

    未指定 Provider 时沿用按模型名自动匹配的既有行为；指定 Provider 时优先使用该 Provider 的预设
    模型价格，未命中则回退到该 Provider 对应能力的默认模板，并要求管理员补填价格。
    """

    explicit_template_id = payload.get("template_id")
    explicit_model_type = payload.get("model_type")
    preset_entry = match.entry
    if provider_id is not None and preset_entry is not None and _template_provider_id(match.template_id) != provider_id:
        preset_entry = None
    if provider_id is not None:
        template_id = _resolve_provider_template_id(
            provider_id=provider_id,
            model_name=payload["name"],
            model_type=explicit_model_type,
            explicit_template_id=explicit_template_id,
            preset_template_id=match.template_id if preset_entry is not None else None,
        )
    else:
        template_id = explicit_template_id or match.template_id
    if template_id is None:
        raise ValidationError("未匹配到模型模板，请显式指定 template_id")
    template = get_provider_template_registry().get(template_id)
    if template is None:
        raise ValidationError("模型模板不存在")
    if explicit_model_type:
        return template_id, explicit_model_type, preset_entry
    if preset_entry is not None and match.model_type is not None:
        return template_id, match.model_type, preset_entry
    if template_id == match.template_id and match.model_type is not None:
        return template_id, match.model_type, preset_entry
    return template_id, str(template["model_type"]), preset_entry


def _resolve_provider_template_id(
    *,
    provider_id: str,
    model_name: str,
    model_type: str | None,
    explicit_template_id: str | None,
    preset_template_id: str | None,
) -> str:
    """在指定 Provider 内选择模板：显式模板优先，其次预设条目模板，最后按模型类型或名称推断回退。"""

    templates = _provider_templates(provider_id)
    template_ids = {template["template_id"] for template in templates}
    if explicit_template_id is not None:
        if explicit_template_id not in template_ids:
            raise ValidationError("所选模板不属于该模型 Provider")
        return explicit_template_id
    if preset_template_id is not None:
        return preset_template_id
    wanted_type = model_type or infer_model_type(model_name)
    for template in templates:
        if template["model_type"] == wanted_type:
            return str(template["template_id"])
    if model_type is not None:
        raise ValidationError("所选 Provider 不支持该模型类型")
    for template in templates:
        if template["model_type"] == "text":
            return str(template["template_id"])
    return str(templates[0]["template_id"])


def _provider_templates(provider_id: str) -> list[dict[str, Any]]:
    """返回指定 Provider 的全部模板展示数据，Provider 不存在时抛出校验异常。"""

    templates = [
        template
        for template in get_provider_template_registry().list_views(get_locale())
        if template.get("provider_id") == provider_id
    ]
    if not templates:
        raise ValidationError("模型 Provider 不存在")
    return templates


def _template_provider_id(template_id: str | None) -> str | None:
    """读取模板声明的 Provider 标识，模板不存在时返回空。"""

    if not template_id:
        return None
    template = get_provider_template_registry().get_view(template_id, get_locale())
    return template.get("provider_id") if isinstance(template, dict) else None


def _provider_summaries() -> list[dict[str, object]]:
    """按 Provider 聚合模板支持的模型类型，保持模板声明顺序。"""

    grouped: dict[str, dict[str, object]] = {}
    for template in get_provider_template_registry().list_views(get_locale()):
        provider_id = template.get("provider_id")
        if not isinstance(provider_id, str) or not provider_id:
            continue
        summary = grouped.get(provider_id)
        if summary is None:
            summary = {
                "provider_id": provider_id,
                "provider_name": template.get("provider_name"),
                "provider_logo_url": template.get("provider_logo_url"),
                "model_types": [],
            }
            grouped[provider_id] = summary
        model_types = summary["model_types"]
        model_type = str(template["model_type"])
        if isinstance(model_types, list) and model_type not in model_types:
            model_types.append(model_type)
    return list(grouped.values())


def _catalog_pricing_rules(match: CatalogMatch, template_rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """把目录声明的公开单价覆盖到模板默认规则的对应计费项上。

    文本模型按计费类别逐项覆盖模板默认单价；图片模型默认改用按图片 token 计费，但若所选模板
    已声明按次/按张计费项（例如 OpenAI 按次模板），则保留模板默认的分档规则与单价。
    目录未命中或未提供某计费类别的单价时保留模板默认单价。
    """

    entry = match.entry
    if entry is None:
        return template_rules
    if entry.model_type == "image":
        if _declares_image_request_pricing(template_rules):
            return template_rules
        return _image_pricing_rules(entry)
    amounts = {
        "input_text_tokens": entry.input_price,
        "cache_write_input_text_tokens": entry.cache_write_price,
        "cached_input_text_tokens": entry.cached_input_price,
        "output_text_tokens": entry.output_price,
    }
    for rule in template_rules:
        rule["currency"] = entry.currency
        items = rule.get("items")
        for item in items if isinstance(items, list) else []:
            price = amounts.get(item.get("kind")) if isinstance(item, dict) else None
            if price is not None:
                item["unit_amount"] = price
    return template_rules


def _declares_image_request_pricing(template_rules: list[dict[str, Any]]) -> bool:
    """判断模板默认规则是否按请求次数或输出张数计费。"""

    request_kinds = {PricingItemKind.request_fixed.value, PricingItemKind.output_image_count.value}
    return any(
        item.get("kind") in request_kinds
        for rule in template_rules
        if isinstance(rule, dict)
        for item in (rule.get("items") or [])
        if isinstance(item, dict)
    )


def _image_pricing_rules(entry: ModelPricingEntry) -> list[dict[str, Any]]:
    """按目录的图片 token 单价与估算参数生成图片按 token 计费的默认定价规则。

    平台图片 token 计费要求输入与输出两项同时存在且各自声明估算参数，因此这里生成一条完整
    规则，替换图片模板默认的按次计费规则。
    """

    return [
        {
            "name": "按图片 token 计费",
            "priority": 10,
            "conditions": [],
            "currency": entry.currency,
            "items": [
                {
                    "label": "输入图片 token",
                    "position": 0,
                    "kind": PricingItemKind.input_image_tokens.value,
                    "source_fields": [],
                    "free_quantity": 0,
                    "unit_amount": entry.input_price,
                    "estimate_config": entry.input_image_estimate_config(),
                },
                {
                    "label": "输出图片 token",
                    "position": 1,
                    "kind": PricingItemKind.output_image_tokens.value,
                    "source_fields": [],
                    "free_quantity": 0,
                    "unit_amount": entry.output_price,
                    "estimate_config": entry.output_image_estimate_config(),
                },
            ],
        }
    ]


def _long_context_modifiers(entry: ModelPricingEntry | None) -> list[dict[str, Any]]:
    """按目录声明的长上下文阈值与倍率生成输入、输出两条加价修正项。

    修正项按乘法叠加，因此输入类与输出类各用一条修正项并以计费项类别限定作用范围，
    条件统一为输入 token 超过阈值。目录未声明阈值或对应倍率时返回空列表。
    """

    if entry is None or entry.long_context_threshold is None:
        return []
    conditions: list[dict[str, Any]] = [
        {"field": "prompt_tokens", "operator": "gte", "value": entry.long_context_threshold + 1}
    ]
    modifiers: list[dict[str, Any]] = []
    if entry.long_context_input_multiplier is not None:
        modifiers.append(
            {
                "name": "长上下文输入加价",
                "priority": 10,
                "conditions": deepcopy(conditions),
                "effect_type": "multiplier",
                "effect_payload": {"factor": entry.long_context_input_multiplier},
                "scope_type": "item_kind",
                "scope_item_kinds": list(_TEXT_INPUT_ITEM_KINDS),
            }
        )
    if entry.long_context_output_multiplier is not None:
        modifiers.append(
            {
                "name": "长上下文输出加价",
                "priority": 20,
                "conditions": deepcopy(conditions),
                "effect_type": "multiplier",
                "effect_payload": {"factor": entry.long_context_output_multiplier},
                "scope_type": "item_kind",
                "scope_item_kinds": list(_TEXT_OUTPUT_ITEM_KINDS),
            }
        )
    return modifiers


def _batch_preview_item(name: str, *, provider_id: str | None, model_type: str | None) -> dict[str, Any]:
    """构造批量预览中的单个模型结果，解析失败时返回带错误信息的最小项。"""

    try:
        preview = _match_preview(get_model_catalog().match(name), provider_id=provider_id, model_type=model_type)
    except (ValidationError, ValueError) as exc:
        return {
            "model_name": name,
            "matched": False,
            "requires_pricing_input": False,
            "match_type": "none",
            "template_id": None,
            "model_type": None,
            "provider_id": provider_id,
            "provider_name": None,
            "provider_logo_url": None,
            "pricing_summary": [],
            "pricing_rules": [],
            "pricing_modifiers": [],
            "pricing_fields": [],
            "input_schema": None,
            "error": str(exc),
        }
    return {
        "model_name": name,
        "matched": bool(preview["matched"]),
        "requires_pricing_input": bool(preview["requires_pricing_input"]),
        "match_type": str(preview["match_type"]),
        "template_id": preview["template_id"],
        "model_type": preview["model_type"],
        "provider_id": preview["provider_id"],
        "provider_name": preview["provider_name"],
        "provider_logo_url": preview["provider_logo_url"],
        "pricing_summary": _pricing_summary(preview["pricing_rules"]) if preview["matched"] else [],
        "pricing_rules": preview["pricing_rules"],
        "pricing_modifiers": preview["pricing_modifiers"],
        "pricing_fields": preview["pricing_fields"],
        "input_schema": preview["input_schema"],
        "error": None,
    }


def _pricing_summary(rules: Any) -> list[dict[str, Any]]:
    """把定价规则折叠为逐个计费项的价格摘要，供批量列表直接展示。"""

    summary: list[dict[str, Any]] = []
    for rule in rules if isinstance(rules, list) else []:
        if not isinstance(rule, dict):
            continue
        currency = rule.get("currency") if isinstance(rule.get("currency"), str) else None
        items = rule.get("items") if isinstance(rule.get("items"), list) else []
        for item in items:
            if not isinstance(item, dict):
                continue
            kind = item.get("kind")
            amount = item.get("unit_amount")
            if kind == PricingItemKind.input_video_duration.value and amount is None:
                continue
            summary.append(
                {
                    "kind": kind if isinstance(kind, str) else None,
                    "label": item.get("label") if isinstance(item.get("label"), str) else None,
                    "unit_amount": None if amount is None else str(amount),
                    "currency": currency or "USD",
                }
            )
    return summary


def _match_preview(
    match: CatalogMatch, *, provider_id: str | None = None, model_type: str | None = None
) -> dict[str, object]:
    """构造模型名匹配结果的预览视图，未匹配时除匹配类型外均为空。

    指定 ``provider_id`` 时只采用该 Provider 的预设价格；未命中预设时返回该 Provider 默认模板的定价
    骨架并将 ``requires_pricing_input`` 置为真，供创建表单要求管理员填写单价。
    """

    preview: dict[str, object] = {
        "model_name": match.model_name,
        "normalized_name": match.normalized_name,
        "match_type": match.match_type,
        "matched": False,
        "template_id": None,
        "model_type": None,
        "provider_id": provider_id,
        "provider_name": None,
        "provider_logo_url": None,
        "currency": None,
        "source_url": None,
        "price_updated_at": None,
        "note": None,
        "pricing_rules": [],
        "pricing_modifiers": [],
        "pricing_fields": [],
        "input_schema": None,
        "requires_pricing_input": False,
    }
    if provider_id is None and match.template_id is None:
        return preview
    template_id, model_type_value, preset_entry = _resolve_model_template(
        {"name": match.model_name, "model_type": model_type}, match=match, provider_id=provider_id
    )
    resolved_provider_id, provider_name, provider_logo_url = _provider_identities().get(template_id, (None, None, None))
    rules = (
        _catalog_pricing_rules(match, _template_pricing_rules(template_id))
        if preset_entry is not None
        else _template_pricing_rules(template_id)
    )
    preview.update(
        {
            "match_type": match.match_type if preset_entry is not None or provider_id is None else "provider_fallback",
            "matched": preset_entry is not None,
            "template_id": template_id,
            "model_type": model_type_value,
            "provider_id": provider_id or resolved_provider_id,
            "provider_name": provider_name,
            "provider_logo_url": provider_logo_url,
            "pricing_rules": rules,
            "pricing_modifiers": _long_context_modifiers(preset_entry),
            "requires_pricing_input": preset_entry is None or not _pricing_configured(rules),
        }
    )
    if preset_entry is not None:
        preview["currency"] = preset_entry.currency
        preview["source_url"] = preset_entry.source_url
        preview["price_updated_at"] = preset_entry.price_updated_at
        preview["note"] = preset_entry.note
    contract = _build_input_contract(template_id, model_type_value, None)
    preview["pricing_fields"] = _merge_pricing_fields(contract, [], rules)
    preview["input_schema"] = _contract_input_schema(contract)
    return preview


def update_model(session: Session, *, model_id: UUID, **payload: Any) -> dict[str, object]:
    model = _get_live_model_for_update(session, model_id)
    effective_contract = _resolve_input_contract(
        current_template_id=model.template_id,
        current_model_type=model.model_type,
        current_contract=model.input_contract,
        payload=payload,
    )
    candidate = Model(
        **{
            key: effective_contract if key == "input_contract" else payload.get(key, getattr(model, key))
            for key in (
                "name",
                "description",
                "model_type",
                "template_id",
                "input_contract",
                "pricing_fields",
                "default_concurrency_limit",
                "active",
            )
        }
    )
    _validate_template(candidate.template_id, candidate.model_type)
    if ModelCrud(session).get_by_name(candidate.name, exclude_model_id=model.id) is not None:
        raise ValidationError("模型名称已存在")
    _validate_model(candidate)
    # 类型或模板变更会改变计费主体项口径，存量方案必然不再适用：按新模板整体重建
    if candidate.model_type != model.model_type or candidate.template_id != model.template_id:
        return _rebuild_model_pricing(session, model=model, payload=payload, effective_contract=effective_contract)
    rule_crud = PricingRuleCrud(session)
    modifier_crud = PricingModifierCrud(session)
    rules = rule_crud.list_for_model(model.id)
    pricing_item_crud = PricingItemCrud(session)
    items = pricing_item_crud.list_for_rules([rule.id for rule in rules])
    modifiers = [modifier for rule in rules for modifier in modifier_crud.list_for_rule(rule.id)]
    validate_configuration(
        channels=[],
        rules=rules,
        modifiers=modifiers,
        items=items,
        allowed_fields=candidate.pricing_fields,
        input_schema=_input_schema(candidate),
        standardized_projection=_projection(candidate),
        material_fields=_material_fields(candidate),
        derived_pricing_fields=_derived_pricing_fields(candidate),
        model_type=candidate.model_type,
    )
    old_name = model.name
    for key, value in payload.items():
        if key == "input_contract":
            continue
        setattr(model, key, value)
    model.input_contract = effective_contract
    if model.name != old_name:
        _rename_channel_model_reference(session, old_name=old_name, new_name=model.name)
    return {"id": str(model.id)}


def _rebuild_model_pricing(
    session: Session, *, model: Model, payload: dict[str, Any], effective_contract: dict[str, Any]
) -> dict[str, object]:
    """模型类型或模板变更后重建定价方案。

    旧方案连同计费项与修正项一起逻辑删除留档，再按新模板在原有令牌分组播种默认定价规则，
    分组已删除或已停用时回落系统默认分组。返回的 ``pricing_configured`` 供管理台提示补填单价。
    """

    rule_crud = PricingRuleCrud(session)
    group_ids = list(dict.fromkeys(rule.token_group_id for rule in rule_crud.list_for_model(model.id)))
    # 计费项与修正项按方案 ID 归档，必须在方案自身归档前执行，否则子查询取不到方案
    PricingItemCrud(session).soft_delete_for_model(model.id)
    PricingModifierCrud(session).soft_delete_for_model(model.id)
    rule_crud.soft_delete_for_model(model.id)
    old_name = model.name
    for key, value in payload.items():
        if key == "input_contract":
            continue
        setattr(model, key, value)
    model.input_contract = effective_contract
    if model.name != old_name:
        _rename_channel_model_reference(session, old_name=old_name, new_name=model.name)
    match = get_model_catalog().match(model.name)
    default_rules = _catalog_pricing_rules(match, _template_pricing_rules(model.template_id))
    model.pricing_fields = _merge_pricing_fields(model.input_contract, list(model.pricing_fields or []), default_rules)
    validate_configuration(
        channels=[],
        rules=[],
        modifiers=[],
        allowed_fields=model.pricing_fields,
        input_schema=_input_schema(model),
        standardized_projection=_projection(model),
        material_fields=_material_fields(model),
        derived_pricing_fields=_derived_pricing_fields(model),
        model_type=model.model_type,
    )
    ModelCrud(session).flush()
    _seed_default_pricing_rules(
        session,
        model=model,
        rules=default_rules,
        modifiers=_long_context_modifiers(match.entry),
        group_ids=_active_group_ids(session, group_ids),
    )
    return {"id": str(model.id), "pricing_configured": _pricing_configured(default_rules)}


def _active_group_ids(session: Session, group_ids: list[int]) -> list[int]:
    """重建定价方案的目标令牌分组：只保留仍存在且启用的分组，全部失效时回落默认分组。"""

    if not group_ids:
        return []
    groups = TokenGroupCrud(session).list_groups_by_ids(set(group_ids))
    active_ids = {group.id for group in groups if group.is_active}
    return [group_id for group_id in group_ids if group_id in active_ids]


def _validate_template(template_id: str | None, model_type: str) -> None:
    if template_id is None:
        raise ValidationError("模型模板不能为空")
    template = get_provider_template_registry().get(template_id)
    if template is None:
        raise ValidationError("模型模板不存在")
    if template["model_type"] != model_type:
        raise ValidationError("模型模板类型与模型类型不一致")


def _build_input_contract(template_id: str, model_type: str, override: dict[str, Any] | None) -> dict[str, Any]:
    _validate_template(template_id, model_type)
    template = get_provider_template_registry().get(template_id)
    if template is None:
        raise ValidationError("模型模板不存在")
    base_contract = {
        "input_schema": template["input_schema"],
        "projection": {},
        "materials": template.get("material_fields", {}),
        "derived_pricing_fields": template.get("derived_pricing_fields", []),
    }
    return _deep_merge(base_contract, override or {})


def _resolve_input_contract(
    *,
    current_template_id: str | None,
    current_model_type: str,
    current_contract: dict[str, Any] | None,
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    template_changed = "template_id" in payload and payload["template_id"] != current_template_id
    if template_changed:
        return _build_input_contract(
            payload["template_id"], payload.get("model_type", current_model_type), payload.get("input_contract")
        )
    if "input_contract" in payload and payload["input_contract"] is not None:
        return _deep_merge(current_contract or {}, payload["input_contract"])
    return current_contract


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def _template_pricing_rules(template_id: str | None) -> list[dict[str, Any]]:
    """读取模板声明的默认定价规则（按尺寸档位等预设的完整方案）。"""

    if not template_id:
        return []
    template = get_provider_template_registry().get(template_id)
    rules = template.get("default_pricing_rules") if isinstance(template, dict) else None
    return deepcopy(rules) if isinstance(rules, list) else []


def _merge_pricing_fields(contract: dict[str, Any] | None, fields: list[str], rules: list[dict[str, Any]]) -> list[str]:
    """把模板定价规则引用的字段并入模型价格白名单，保证默认规则可校验、可生效。"""

    schema = _contract_input_schema(contract) or {}
    projection = contract.get("projection") if isinstance(contract, dict) else None
    declarable = set(schema.get("properties") or {}) | set((projection or {}).keys())
    merged = list(dict.fromkeys(fields))
    for name in _rule_referenced_fields(rules):
        if name in declarable and name not in merged:
            merged.append(name)
    return merged


def _rule_referenced_fields(rules: list[dict[str, Any]]) -> list[str]:
    """按出现顺序收集规则条件与计费项计量来源引用的字段。"""

    fields: list[str] = []
    for rule in rules:
        conditions = rule.get("conditions") if isinstance(rule, dict) else None
        for condition in conditions if isinstance(conditions, list) else []:
            name = condition.get("field") if isinstance(condition, dict) else None
            if isinstance(name, str) and name not in fields:
                fields.append(name)
        items = rule.get("items") if isinstance(rule, dict) else None
        for item in items if isinstance(items, list) else []:
            source_fields = item.get("source_fields") if isinstance(item, dict) else None
            for name in source_fields if isinstance(source_fields, list) else []:
                if isinstance(name, str) and name not in fields:
                    fields.append(name)
    return fields


def _pricing_configured(rules: list[dict[str, Any]]) -> bool:
    """判断待播种的模板定价规则是否已带齐单价。

    输入视频时长项按方案内唯一的输出视频时长项计价，自身单价允许为空，不计入未定价。
    返回 ``False`` 表示模型创建后管理员还需在定价面板补填单价，此时生成请求会被拦下。
    """

    if not rules:
        return False
    for rule in rules:
        items = rule.get("items") if isinstance(rule, dict) else None
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict):
                continue
            if item.get("kind") == PricingItemKind.input_video_duration.value:
                continue
            if item.get("unit_amount") is None:
                return False
    return True


def _seed_default_pricing_rules(
    session: Session,
    *,
    model: Model,
    rules: list[dict[str, Any]],
    modifiers: list[dict[str, Any]] | None = None,
    group_ids: list[int] | None = None,
) -> None:
    """在目标令牌分组下为新建模型生成模板预设的定价规则与目录声明的分档加价修正项。

    未指定 ``group_ids`` 时沿用系统默认分组；指定时按传入顺序去重后逐个播种，
    每个分组各得到一套相互独立的规则副本。
    """

    if not rules:
        return
    groups = _resolve_seed_groups(session, group_ids)
    if not groups:
        return
    created_rule_ids: list[UUID] = []
    rule_crud = PricingRuleCrud(session)
    for group in groups:
        for rule in rules:
            items = [deepcopy(item) for item in rule.get("items", [])]
            if not items:
                continue
            payload: dict[str, Any] = {
                "model_id": model.id,
                "token_group_id": group.id,
                "name": rule["name"],
                "conditions": deepcopy(rule.get("conditions", [])),
                "items": items,
            }
            # 目录条目声明了币种时跟随条目，否则沿用定价规则自身的默认币种。
            currency = rule.get("currency")
            if isinstance(currency, str) and currency:
                payload["currency"] = currency
            created = _create_pricing_rule_for_model(session, model=model, payload=payload)
            # 会话关闭 autoflush，逐条 flush 才能让后续规则按已落库的优先级顺延取号。
            rule_crud.flush()
            created_rule_ids.append(UUID(str(created["id"])))
    if not modifiers or not created_rule_ids:
        return
    # 计费项此时尚未落库，先 flush 再播种修正项，否则修正项的方案内计费项校验取不到数据。
    PricingItemCrud(session).flush()
    modifier_crud = PricingModifierCrud(session)
    for rule_id in created_rule_ids:
        for modifier in modifiers:
            modifier_payload = deepcopy(modifier)
            modifier_payload.pop("priority", None)
            create_pricing_modifier(session, pricing_rule_id=rule_id, **modifier_payload)
            # 同理逐条 flush，避免同一方案内的修正项取到相同优先级。
            modifier_crud.flush()


def _resolve_seed_groups(session: Session, group_ids: list[int] | None) -> list[TokenGroup]:
    """解析默认定价规则的目标令牌分组，未指定时回退到系统默认分组。"""

    group_crud = TokenGroupCrud(session)
    ordered_ids = list(dict.fromkeys(group_ids)) if group_ids else []
    if not ordered_ids:
        default_group = group_crud.get_default_group()
        return [default_group] if default_group is not None else []
    groups_by_id = {group.id: group for group in group_crud.list_groups_by_ids(set(ordered_ids))}
    resolved: list[TokenGroup] = []
    for group_id in ordered_ids:
        group = groups_by_id.get(group_id)
        if group is None:
            raise ValidationError("令牌分组不存在")
        if not group.is_active:
            raise ValidationError(
                f"令牌分组已停用：{group.name}", code="token_group.disabled", params={"name": group.name}
            )
        resolved.append(group)
    return resolved


def update_model_status(session: Session, *, model_id: UUID, active: bool) -> dict[str, object]:
    model = _get_live_model_for_update(session, model_id)
    model.active = active
    return {"id": str(model.id), "active": model.active}


def delete_model(session: Session, *, model_id: UUID) -> None:
    model = _get_live_model_for_update(session, model_id)
    channel_crud = ChannelCrud(session)
    route_crud = ModelRouteCrud(session)
    referencing = {channel.id: channel for channel in channel_crud.list_referencing_model(model.name)}
    for channel_id in route_crud.list_channel_ids_for_model(model.id):
        if channel_id in referencing:
            continue
        channel = channel_crud.get(channel_id)
        if channel is not None:
            referencing[channel_id] = channel
    model.is_del = True
    route_crud.soft_delete_for_model(model.id)
    PricingModifierCrud(session).soft_delete_for_model(model.id)
    PricingItemCrud(session).soft_delete_for_model(model.id)
    PricingRuleCrud(session).soft_delete_for_model(model.id)
    for channel in referencing.values():
        _prune_channel_model_references(session, channel, removed_name=model.name)


def _rename_channel_model_reference(session: Session, *, old_name: str, new_name: str) -> None:
    """模型改名时同步渠道里按模型名保存的引用，避免渠道残留失效的旧名字。"""

    for channel in ChannelCrud(session).list_referencing_model(old_name):
        channel.supported_models = [new_name if name == old_name else name for name in channel.supported_models]
        if old_name in channel.model_mapping:
            channel.model_mapping = {
                (new_name if name == old_name else name): mapping for name, mapping in channel.model_mapping.items()
            }


def _prune_channel_model_references(session: Session, channel: Channel, *, removed_name: str) -> None:
    """移除渠道对已删除模型的引用，并顺带清理无法对应任何有效模型的失效名字。"""

    names = [name for name in channel.supported_models if name != removed_name]
    live_names = {model.name for model in ModelCrud(session).list_by_names(names)}
    channel.supported_models = [name for name in names if name in live_names]
    channel.model_mapping = {name: mapping for name, mapping in channel.model_mapping.items() if name in live_names}


def _next_priority_in_scope(existing: Iterable[PricingRule | PricingModifier], *, conditional: bool) -> int:
    """分配定价优先级：有条件规则插到无条件兜底规则之前，无条件规则或空范围追加到末尾。"""

    entries = list(existing)
    priorities = {entry.priority for entry in entries}
    fallback_priorities = [entry.priority for entry in entries if not entry.conditions]
    if conditional and fallback_priorities:
        candidate = min(fallback_priorities) - 1
        while candidate in priorities:
            candidate -= 1
        return candidate
    return max(priorities, default=0) + 1


def create_pricing_rule(session: Session, **payload: Any) -> dict[str, object]:
    model = _get_live_model(session, payload["model_id"])
    return _create_pricing_rule_for_model(session, model=model, payload=payload)


def _create_pricing_rule_for_model(session: Session, *, model: Model, payload: dict[str, Any]) -> dict[str, object]:
    item_payloads = payload.pop("items")
    payload.pop("priority", None)
    rule_crud = PricingRuleCrud(session)
    # 锁定模型行以串行化同一模型下的规则写入，避免并发请求取到相同 priority。
    ModelCrud(session).get_for_update(payload["model_id"])
    payload["priority"] = _next_priority_in_scope(
        rule_crud.list_in_scope(model_id=payload["model_id"], token_group_id=payload["token_group_id"]),
        conditional=bool(payload.get("conditions")),
    )
    rule = PricingRule(**payload)
    items = _build_pricing_items(rule.id, item_payloads)
    validate_configuration(
        channels=[],
        rules=[rule],
        modifiers=[],
        items=items,
        allowed_fields=model.pricing_fields,
        input_schema=_input_schema(model),
        standardized_projection=_projection(model),
        material_fields=_material_fields(model),
        derived_pricing_fields=_derived_pricing_fields(model),
        model_type=model.model_type,
    )
    rule_crud.add(rule)
    PricingItemCrud(session).add_many(items)
    return {"id": str(rule.id)}


def update_pricing_rule(session: Session, *, rule_id: UUID, **payload: Any) -> dict[str, object]:
    rule_crud = PricingRuleCrud(session)
    rule = rule_crud.get_for_update(rule_id)
    if rule is None:
        raise NotFoundError("价格规则不存在")
    item_payloads = payload.pop("items")
    payload.pop("priority", None)
    model_id = payload.get("model_id", rule.model_id)
    token_group_id = payload.get("token_group_id", rule.token_group_id)
    # 先锁目标模型，再在目标分组内取号，避免并发移动方案时占用相同 priority。
    model = _get_live_model_for_update(session, model_id)
    # 优先级只由服务端在同模型同分组内顺延；跨模型或分组移动方案时重新取号，避免占用目标范围已有值。
    priority = rule.priority
    if (model_id, token_group_id) != (rule.model_id, rule.token_group_id):
        priority = _next_priority_in_scope(
            rule_crud.list_in_scope(model_id=model_id, token_group_id=token_group_id),
            conditional=bool(payload.get("conditions", rule.conditions)),
        )
    candidate = PricingRule(
        id=rule.id,
        priority=priority,
        **{
            key: payload.get(key, getattr(rule, key))
            for key in (
                "model_id",
                "token_group_id",
                "name",
                "conditions",
                "currency",
                "active",
            )
        },
    )
    item_crud = PricingItemCrud(session)
    existing_by_position = {item.position: item for item in item_crud.list_for_rule(rule.id)}
    candidate_items = _build_pricing_items(rule.id, item_payloads, existing_by_position)
    modifiers = PricingModifierCrud(session).list_for_rule(rule.id)
    validate_configuration(
        channels=[],
        rules=[candidate],
        modifiers=modifiers,
        items=candidate_items,
        allowed_fields=model.pricing_fields,
        input_schema=_input_schema(model),
        standardized_projection=_projection(model),
        material_fields=_material_fields(model),
        derived_pricing_fields=_derived_pricing_fields(model),
        model_type=model.model_type,
    )
    for key, value in payload.items():
        setattr(rule, key, value)
    rule.priority = priority
    item_crud.sync_for_rule(rule.id, candidate_items)
    return {"id": str(rule.id)}


def delete_pricing_rule(session: Session, *, rule_id: UUID) -> None:
    rule = PricingRuleCrud(session).get_for_update(rule_id)
    if rule is None:
        raise NotFoundError("价格规则不存在")
    rule.is_del = True
    PricingModifierCrud(session).soft_delete_for_rule(rule.id)
    PricingItemCrud(session).soft_delete_for_rule(rule.id)


def create_pricing_modifier(session: Session, **payload: Any) -> dict[str, object]:
    rule = PricingRuleCrud(session).get_for_update(payload["pricing_rule_id"])
    if rule is None:
        raise NotFoundError("价格规则不存在")
    payload.pop("priority", None)
    modifier_crud = PricingModifierCrud(session)
    payload["priority"] = _next_priority_in_scope(
        modifier_crud.list_for_rule(payload["pricing_rule_id"]),
        conditional=bool(payload.get("conditions")),
    )
    modifier = PricingModifier(**payload)
    model = _get_live_model(session, rule.model_id)
    items = PricingItemCrud(session).list_for_rule(rule.id)
    validate_configuration(
        channels=[],
        rules=[rule],
        modifiers=[modifier],
        items=items,
        allowed_fields=model.pricing_fields,
        input_schema=_input_schema(model),
        standardized_projection=_projection(model),
        material_fields=_material_fields(model),
        derived_pricing_fields=_derived_pricing_fields(model),
        model_type=model.model_type,
    )
    modifier_crud.add(modifier)
    return {"id": str(modifier.id)}


def update_pricing_modifier(session: Session, *, modifier_id: UUID, **payload: Any) -> dict[str, object]:
    modifier_crud = PricingModifierCrud(session)
    modifier = modifier_crud.get_for_update(modifier_id)
    if modifier is None:
        raise NotFoundError("价格修正不存在")
    payload.pop("priority", None)
    pricing_rule_id = payload.get("pricing_rule_id") or modifier.pricing_rule_id
    # 锁定目标方案，串行化同一方案内的修正项取号，避免并发时占用相同 priority。
    rule = PricingRuleCrud(session).get_for_update(pricing_rule_id)
    if rule is None:
        raise NotFoundError("价格规则不存在")
    # 修正项归属方案变化时在目标方案内重新顺延优先级，避免与已有修正项冲突。
    priority = modifier.priority
    if pricing_rule_id != modifier.pricing_rule_id:
        priority = _next_priority_in_scope(
            modifier_crud.list_for_rule(pricing_rule_id),
            conditional=bool(payload.get("conditions", modifier.conditions)),
        )
    candidate = PricingModifier(
        priority=priority,
        **{
            key: payload.get(key, getattr(modifier, key))
            for key in (
                "name",
                "conditions",
                "effect_type",
                "effect_payload",
                "scope_type",
                "scope_item_ids",
                "scope_item_kinds",
                "active",
            )
        },
        pricing_rule_id=pricing_rule_id,
    )
    model = _get_live_model(session, rule.model_id)
    items = PricingItemCrud(session).list_for_rule(rule.id)
    validate_configuration(
        channels=[],
        rules=[rule],
        modifiers=[candidate],
        items=items,
        allowed_fields=model.pricing_fields,
        input_schema=_input_schema(model),
        standardized_projection=_projection(model),
        material_fields=_material_fields(model),
        derived_pricing_fields=_derived_pricing_fields(model),
        model_type=model.model_type,
    )
    for key, value in payload.items():
        if key == "pricing_rule_id" and value is None:
            continue
        setattr(modifier, key, value)
    modifier.priority = priority
    return {"id": str(modifier.id)}


def delete_pricing_modifier(session: Session, *, modifier_id: UUID) -> None:
    modifier = PricingModifierCrud(session).get_for_update(modifier_id)
    if modifier is None:
        raise NotFoundError("价格修正不存在")
    modifier.is_del = True


def _validate_channel(channel: Channel) -> None:
    if not channel.base_url.startswith(("http://", "https://")):
        raise ValueError("渠道 URL 必须使用 HTTP 或 HTTPS 协议")
    if "base_url" in channel.config or "api_key" in channel.config:
        raise ValueError("渠道运行选项不允许包含地址或认证数据")
    if channel.weight <= 0:
        raise ValueError("渠道权重必须为正整数")
    if len(channel.supported_models) != len(set(channel.supported_models)):
        raise ValueError("渠道模型列表不能重复")
    if any(not isinstance(name, str) or not name for name in channel.supported_models):
        raise ValueError("渠道模型列表不合法")
    if set(channel.model_mapping) - set(channel.supported_models):
        raise ValueError("渠道模型映射包含未启用模型")
    if any(not isinstance(name, str) or not name for name in channel.model_mapping.values()):
        raise ValueError("渠道模型映射必须为上游模型名")
    if len(channel.token_group_ids) != len(set(channel.token_group_ids)) or any(
        not isinstance(group_id, int) or group_id <= 0 for group_id in channel.token_group_ids
    ):
        raise ValueError("渠道令牌分组不合法")


def _validate_model(model: Model) -> None:
    if model.model_type not in {"text", "image", "video", "audio"}:
        raise ValueError("模型类型不支持")
    if model.model_type in {"text", "image", "video"} and not isinstance(model.input_contract, dict):
        raise ValueError("该模型类型必须配置请求契约")
    if model.model_type == "audio" and model.input_contract is not None:
        raise ValueError("音频模型不能配置请求契约")


def _input_schema(model: Model) -> dict[str, Any] | None:
    return _contract_input_schema(getattr(model, "input_contract", None))


def _projection(model: Model) -> dict[str, Any] | None:
    return _contract_projection(getattr(model, "input_contract", None))


def _contract_input_schema(contract: Any) -> dict[str, Any] | None:
    return contract.get("input_schema") if isinstance(contract, dict) else None


def _contract_projection(contract: Any) -> dict[str, Any] | None:
    return contract.get("projection") if isinstance(contract, dict) else None


def _material_fields(model: Model) -> dict[str, Any] | None:
    contract = getattr(model, "input_contract", None)
    return contract.get("materials") if isinstance(contract, dict) else None


def _derived_pricing_fields(model: Model) -> list[dict[str, Any]] | None:
    contract = getattr(model, "input_contract", None)
    return contract.get("derived_pricing_fields") if isinstance(contract, dict) else None


def _sync_channel_routes(session: Session, channel: Channel) -> None:
    route_crud = ModelRouteCrud(session)
    models_by_name = {model.name: model for model in ModelCrud(session).list_by_names(channel.supported_models)}
    desired: set[tuple[UUID, int]] = set()
    for model_name in channel.supported_models:
        model = models_by_name.get(model_name)
        if model is None:
            raise ValidationError(
                f"渠道引用的模型不存在或已被删除：{model_name}",
                code="contract.model_reference_deleted",
                params={"name": model_name},
            )
        for token_group_id in channel.token_group_ids:
            desired.add((model.id, token_group_id))
    existing = route_crud.list_for_channel(channel.id)
    existing_by_key = {(route.model_id, route.token_group_id): route for route in existing}
    for key, route in existing_by_key.items():
        if key not in desired:
            route.is_del = True
    for model_id, token_group_id in desired:
        route = existing_by_key.get((model_id, token_group_id))
        if route is None:
            route_crud.add(
                ModelRoute(
                    model_id=model_id,
                    channel_id=channel.id,
                    token_group_id=token_group_id,
                    priority=channel.priority,
                    weight=channel.weight,
                    enabled=channel.active,
                    healthy=channel.healthy,
                )
            )
        else:
            route.is_del = False
            route.priority = channel.priority
            route.weight = channel.weight
            route.enabled = channel.active
            route.healthy = channel.healthy


def _channel_view(channel: Channel, *, groups_by_id: dict[int, TokenGroup] | None = None) -> dict[str, object]:
    token_groups = []
    if groups_by_id is not None:
        token_groups = [
            {"id": group.id, "name": group.name}
            for group_id in channel.token_group_ids
            if (group := groups_by_id.get(group_id)) is not None
        ]
    return {
        "id": str(channel.id),
        "name": channel.name,
        "active": channel.active,
        "base_url": channel.base_url,
        "config": channel.config,
        "supported_models": channel.supported_models,
        "token_group_ids": channel.token_group_ids,
        "token_groups": token_groups,
        "model_mapping": channel.model_mapping,
        "param_override": channel.param_override,
        "header_override": channel.header_override,
        "latest_test_snapshot": channel.latest_test_snapshot,
        "priority": channel.priority,
        "weight": channel.weight,
        "healthy": channel.healthy,
    }


def _reset_channel_route_runtime(session: Session, channel_id: UUID) -> None:
    """管理员调整初始权重或优先级后清除路由运行时权重，让新配置立即生效。"""

    route_ids = [route.id for route in ConfigurationChannelCrud(session).list_routes_for_channel(channel_id=channel_id)]
    try:
        get_channel_runtime().reset_routes(route_ids)
    except Exception:
        logger.warning("渠道路由运行时状态重置失败 channel_id=%s", channel_id, exc_info=True)


def _channel_runtime_view(session: Session, channel: Channel) -> dict[str, object] | None:
    """读取渠道运行时只读状态；Redis 不可用时返回 ``None`` 而不是让详情请求失败。"""

    settings = get_settings()
    if not settings.routing_runtime_enabled:
        return None
    routes = ConfigurationChannelCrud(session).list_routes_for_channel(channel_id=channel.id)
    runtime = get_channel_runtime()
    try:
        route_states = runtime.read_route_states([route.id for route in routes])
        channel_state = runtime.read_channel_state(channel.id)
    except Exception:
        logger.warning("读取渠道运行时状态失败 channel_id=%s", channel.id, exc_info=True)
        return None

    weights = [_float_or_default(route_states.get(route.id, {}).get("w"), route.weight) for route in routes]
    success_rates = [
        value for route in routes if (value := _float_or_none(route_states.get(route.id, {}).get("sr"))) is not None
    ]
    latencies = [
        value for route in routes if (value := _float_or_none(route_states.get(route.id, {}).get("lat"))) is not None
    ]
    open_until_ms = int(channel_state.get("open_until") or 0)
    last_probe_at_ms = int(channel_state.get("last_probe_at") or 0)
    last_probe = None
    if last_probe_at_ms > 0:
        last_probe = {
            "tested_at": datetime.fromtimestamp(last_probe_at_ms / 1000, UTC).isoformat(),
            "succeeded": channel_state.get("last_probe_ok") == "1",
            "latency_ms": int(channel_state.get("last_probe_latency_ms") or 0),
        }
    return {
        "effective_weight": round(sum(weights) / len(weights), 2) if weights else float(channel.weight),
        "initial_weight": channel.weight,
        "state": channel_state.get("state") or "closed",
        "success_rate": round(sum(success_rates) / len(success_rates), 4) if success_rates else None,
        "average_latency_ms": round(sum(latencies) / len(latencies)) if latencies else None,
        "consecutive_failures": int(channel_state.get("fail") or 0),
        "open_until": datetime.fromtimestamp(open_until_ms / 1000, UTC).isoformat() if open_until_ms > 0 else None,
        "auto_disabled_at": channel.auto_disabled_at.isoformat() if channel.auto_disabled_at else None,
        "last_probe": last_probe,
    }


def _float_or_default(value: object, fallback: float) -> float:
    parsed = _float_or_none(value)
    return parsed if parsed is not None else float(fallback)


def _float_or_none(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _provider_identities() -> dict[str, tuple[str | None, str | None, str | None]]:
    """汇总各模板声明的供应商归属，供模型视图展示与供应商过滤复用。

    供应商展示名随请求语言切换，``provider_id``、``provider_logo_url`` 保持稳定标识。
    """

    return {
        template["template_id"]: (
            template.get("provider_id"),
            template.get("provider_name"),
            template.get("provider_logo_url"),
        )
        for template in get_provider_template_registry().list_views(get_locale())
    }


def _model_view(model: Model, *, providers: dict[str, tuple[str | None, str | None, str | None]]) -> dict[str, object]:
    provider_id, provider_name, provider_logo_url = providers.get(model.template_id, (None, None, None))
    data: dict[str, object] = {
        "id": str(model.id),
        "name": model.name,
        "description": model.description,
        "active": model.active,
        "model_type": model.model_type,
        "template_id": model.template_id,
        "provider_id": provider_id,
        "provider_name": provider_name,
        "provider_logo_url": provider_logo_url,
        "input_contract": model.input_contract,
        "pricing_fields": model.pricing_fields,
        "default_concurrency_limit": model.default_concurrency_limit,
    }
    return data


def _pricing_rule_view(rule: PricingRule, *, items: list[PricingItem]) -> dict[str, object]:
    return {
        "id": str(rule.id),
        "model_id": str(rule.model_id),
        "token_group_id": rule.token_group_id,
        "name": rule.name,
        "priority": rule.priority,
        "conditions": rule.conditions,
        "items": [_pricing_item_view(item) for item in items],
        "currency": rule.currency,
        "active": rule.active,
    }


def _pricing_modifier_view(modifier: PricingModifier) -> dict[str, object]:
    return {
        "id": str(modifier.id),
        "pricing_rule_id": str(modifier.pricing_rule_id),
        "name": modifier.name,
        "priority": modifier.priority,
        "conditions": modifier.conditions,
        "effect_type": modifier.effect_type,
        "effect_payload": modifier.effect_payload,
        "scope_type": modifier.scope_type,
        "scope_item_ids": modifier.scope_item_ids,
        "scope_item_kinds": modifier.scope_item_kinds,
        "active": modifier.active,
    }


def _build_pricing_items(
    pricing_rule_id: UUID,
    payloads: list[dict[str, Any]],
    existing_by_position: dict[int, PricingItem] | None = None,
) -> list[PricingItem]:
    """构造计费项，按 position 复用已有项主键以保持身份稳定，其余主键由服务端生成。"""

    existing_by_position = existing_by_position or {}
    items: list[PricingItem] = []
    for payload in payloads:
        existing = existing_by_position.get(payload["position"])
        if existing is None:
            items.append(PricingItem(id=uuid4(), pricing_rule_id=pricing_rule_id, **payload))
        else:
            for key, value in payload.items():
                setattr(existing, key, value)
            items.append(existing)
    _attach_price_source_items(items)
    return items


def _attach_price_source_items(items: list[PricingItem]) -> None:
    """把输入视频时长计费项的单价来源指向方案内唯一的输出视频时长计费项。"""

    inputs = [item for item in items if item.kind == PricingItemKind.input_video_duration.value]
    outputs = [item for item in items if item.kind == PricingItemKind.output_video_duration.value]
    if inputs and len(outputs) != 1:
        raise ValidationError("输入视频时长计费项必须复用方案内唯一的输出视频时长计费项")
    source_id = outputs[0].id if outputs else None
    for item in items:
        item.price_source_item_id = source_id if item.kind == PricingItemKind.input_video_duration.value else None


def _items_by_rule(items: list[PricingItem]) -> dict[UUID, list[PricingItem]]:
    grouped: dict[UUID, list[PricingItem]] = {}
    for item in items:
        grouped.setdefault(item.pricing_rule_id, []).append(item)
    return grouped


def _pricing_item_view(item: PricingItem) -> dict[str, object]:
    return {
        "id": str(item.id),
        "label": item.label,
        "position": item.position,
        "kind": item.kind,
        "source_fields": item.source_fields,
        "estimate_config": item.estimate_config,
        "free_quantity": item.free_quantity,
        "unit_amount": None if item.unit_amount is None else str(item.unit_amount),
        "price_source_item_id": None if item.price_source_item_id is None else str(item.price_source_item_id),
        "active": item.active,
    }
