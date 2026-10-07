"""模型广场查询服务，列表返回基础信息与首个公开分组价格，详情聚合模板、公开分组与分档价格。"""

from collections import defaultdict
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlmodel import Session

from app.bootstrap.container import get_provider_template_registry
from app.core.errors import NotFoundError
from app.core.i18n import get_locale, translate
from app.core.protocols import BEARER_API_KEY_AUTH, model_operations
from app.modules.marketplace.crud.models import ModelMarketplaceCrud
from app.modules.pricing.application.engine import effective_unit_amounts


class ModelMarketplaceApplicationService:
    def __init__(self, session: Session) -> None:
        self._crud = ModelMarketplaceCrud(session)

    def list_models(
        self,
        *,
        page: int,
        page_size: int,
        model_type: str | None,
        keyword: str | None,
    ) -> tuple[int, list[dict[str, Any]]]:
        """分页返回可见模型的基础信息与首个公开分组的价格，供列表卡片标识。"""

        locale = get_locale()
        total, items = self._crud.list_page(
            page=page,
            page_size=page_size,
            model_type=model_type,
            keyword=keyword,
        )
        groups_by_model_id = self._crud.list_public_groups_by_model_ids([model.id for model in items])
        pricing_by_group = self._pricing_by_group(models=items, groups_by_model_id=groups_by_model_id)
        return total, [
            {
                **_base_fields(model, locale),
                **_first_group_fields(model, groups_by_model_id, pricing_by_group, locale),
            }
            for model in items
        ]

    def get_model(self, model_id: UUID) -> dict[str, Any]:
        """返回单个可见模型的完整信息，含模板与公开分组分档价格。"""

        locale = get_locale()
        model = self._crud.get_visible(model_id)
        if model is None:
            raise NotFoundError("模型广场模型不存在")
        groups_by_model_id = self._crud.list_public_groups_by_model_ids([model.id])
        pricing_by_group = self._pricing_by_group(models=[model], groups_by_model_id=groups_by_model_id)
        groups = groups_by_model_id.get(model.id, [])
        data = _base_fields(model, locale)
        template = _template(model, locale)
        data["template"] = _template_payload(template, model_name=model.name)
        data["api_documentation"] = _api_documentation(
            model.model_type,
            template_id=template.get("template_id") if template is not None else None,
        )
        data["groups"] = [_group_payload(model.id, group, pricing_by_group, locale) for group in groups]
        return data

    def _pricing_by_group(self, *, models, groups_by_model_id) -> dict[tuple[UUID, int], list[dict]]:
        group_ids = sorted(
            {group.id for groups in groups_by_model_id.values() for group in groups if group.id is not None}
        )
        multipliers: dict[int, Decimal] = {
            group.id: Decimal(str(group.price_multiplier))
            for groups in groups_by_model_id.values()
            for group in groups
            if group.id is not None
        }
        rules = self._crud.list_active_rules_for_groups(model_ids=[model.id for model in models], group_ids=group_ids)
        rule_ids = [rule.id for rule in rules]
        items_by_rule: dict[UUID, list[Any]] = defaultdict(list)
        for item in self._crud.list_active_items_for_rules(rule_ids):
            items_by_rule[item.pricing_rule_id].append(item)
        modifiers_by_rule: dict[UUID, list[Any]] = defaultdict(list)
        for modifier in self._crud.list_active_modifiers_for_rules(rule_ids):
            modifiers_by_rule[modifier.pricing_rule_id].append(modifier)
        pricing_fields_by_model = {model.id: list(model.pricing_fields) for model in models}
        pricing: dict[tuple[UUID, int], list[dict]] = defaultdict(list)
        for rule in sorted(rules, key=lambda item: item.priority):
            items = items_by_rule.get(rule.id, [])
            effective_amounts = effective_unit_amounts(
                items,
                modifiers_by_rule.get(rule.id, []),
                context={},
                allowed_fields=pricing_fields_by_model.get(rule.model_id, []),
            )
            multiplier = multipliers.get(rule.token_group_id, Decimal(1))
            if multiplier != Decimal(1):
                effective_amounts = {
                    item_id: None
                    if amount is None
                    else (Decimal(str(amount)) * multiplier).quantize(Decimal("0.000001"))
                    for item_id, amount in effective_amounts.items()
                }
            pricing[(rule.model_id, rule.token_group_id)].append(
                _rule_pricing_payload(rule, items, effective_amounts=effective_amounts)
            )
        return pricing


def _template(model, locale: str) -> dict[str, Any] | None:
    """按语言读取公开模型模板，未配置模板时返回空。"""

    if model.template_id is None:
        return None
    return get_provider_template_registry().get_view(model.template_id, locale)


def _base_fields(model, locale: str) -> dict[str, Any]:
    """模型广场基础展示字段，列表与详情共用。

    供应商字段来自模板的公开声明；模板未声明时保持为空，供前端判定该模型没有明确供应商。
    ``description`` 优先取模型自己的介绍，模型未填写时回退模板简介；模板展示文案随语言切换，
    模型介绍与模型名等业务数据保持原样。
    """

    template = _template(model, locale)
    template_summary = template.get("summary") if template is not None else None
    return {
        "model_id": str(model.id),
        "name": model.name,
        "display_name": model.name,
        "type": model.model_type,
        "provider_id": template.get("provider_id") if template is not None else None,
        "provider_name": template.get("provider_name") if template is not None else None,
        "provider_logo_url": template.get("provider_logo_url") if template is not None else None,
        "description": model.description or template_summary,
        "tags": template.get("tags", []) if template is not None else [],
    }


def _first_group_fields(model, groups_by_model_id, pricing_by_group, locale: str) -> dict[str, Any]:
    """列表卡片标识：仅返回首个公开分组及其价格。"""

    groups = groups_by_model_id.get(model.id, [])
    return {"groups": [_group_payload(model.id, groups[0], pricing_by_group, locale)]} if groups else {"groups": []}


def _api_documentation(model_type: str, *, template_id: str | None) -> dict[str, Any]:
    """根据公开模型模板生成调用端点说明，不包含内部渠道配置。"""

    return {
        "auth": dict(BEARER_API_KEY_AUTH),
        "operations": model_operations(template_id=template_id, model_type=model_type),
    }


def _group_payload(model_id: UUID, group, pricing_by_group, locale: str) -> dict[str, Any]:
    """把公开分组投影为展示结构，含该分组的价格。"""

    return {
        "group_id": group.id,
        "name": group.name,
        "pricing": _group_pricing(pricing_by_group.get((model_id, group.id), []), locale),
    }


def _template_payload(template: dict[str, Any] | None, *, model_name: str) -> dict[str, Any] | None:
    """把模板投影为详情展示结构，仅保留公开字段；调用示例的模型名按当前模型拼装。

    ``parameters`` 与 ``material_fields`` 共同描述调用契约：前者是输入字段结构，后者声明哪些字段
    接受素材上传及其类别与单多值，供调用方据此渲染输入并决定 JSON 或 multipart 提交。
    """

    if template is None:
        return None
    return {
        "template_id": template["template_id"],
        "label": template["label"],
        "summary": template["summary"],
        "tags": template["tags"],
        "parameters": template["input_schema"],
        "material_fields": template["material_fields"],
        "example": {"model": model_name, **template["example"]},
    }


def _group_pricing(rules: list[dict[str, Any]], locale: str) -> dict[str, Any]:
    """按分组聚合出展示用价格：有启用规则时返回分档列表，否则回退按量计费。"""

    if not rules:
        return {"type": "usage_based", "message": translate("按实际用量计费", locale)}
    return {"type": "rules", "message": None, "rules": rules}


def _rule_pricing_payload(rule, items, *, effective_amounts) -> dict[str, Any]:
    return {
        "name": rule.name,
        "priority": rule.priority,
        "conditions": rule.conditions,
        "currency": rule.currency,
        "items": [
            {
                "kind": item.kind,
                "label": item.label,
                "unit_amount": None if (amount := effective_amounts.get(item.id)) is None else str(amount),
                "source_fields": list(item.source_fields),
                "free_quantity": item.free_quantity,
            }
            for item in sorted(items, key=lambda item: item.position)
        ],
    }
