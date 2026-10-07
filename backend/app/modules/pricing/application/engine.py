"""多计费项报价引擎。

本模块是按方案、计费项和定向修正项计算单次生成请求费用与报价快照的纯函数集合；不访问数据库、
Provider、钱包或时钟以外的基础设施，时间通过 ``created_at`` 显式传入。计费数量来源包括模型契约
校验后的输出时长字段、实测输入视频时长与输入图片数量。
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, time, timedelta, timezone
from decimal import ROUND_CEILING, Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from app.core.errors import ValidationError
from app.modules.pricing.model.pricing import PricingModifier, PricingRule
from app.modules.pricing.model.pricing_item import PricingItem, PricingItemKind

_OPERATORS = {"eq", "in", "gte", "lte", "between"}
_INTERNAL_PRICING_FIELDS = {
    "shanghai_time",
    "input_image_count",
    "input_video_seconds",
    "image_pixel_count",
    "prompt_tokens",
    "cache_write_tokens",
    "cached_tokens",
    "completion_tokens",
    "resolution",
}
_SHANGHAI_TIMEZONE = timezone(timedelta(hours=8), name="Asia/Shanghai")
_AMOUNT_PRECISION = Decimal("0.000001")
_SNAPSHOT_SCHEMA_VERSION = 1
_TOKENS_PER_MILLION = Decimal("1000000")


@dataclass(frozen=True)
class MaterialFacts:
    """一次请求内归一化素材的计量结果。

    ``image_counts`` 与 ``video_seconds`` 以计费素材字段名为键，分别表示该字段下的图片张数和实测
    视频总秒数；``snapshot`` 为可写入报价快照的脱敏素材事实列表，不含带签名 URL 或上传令牌。
    """

    image_counts: Mapping[str, int] = field(default_factory=dict)
    video_seconds: Mapping[str, Decimal] = field(default_factory=dict)
    image_dimensions: Mapping[str, tuple[tuple[int, int], ...]] = field(default_factory=dict)
    image_tokens: Mapping[str, Decimal] = field(default_factory=dict)
    audio_seconds: Mapping[str, Decimal] = field(default_factory=dict)
    snapshot: tuple[dict[str, object], ...] = ()


@dataclass(frozen=True)
class PricingLineItem:
    """方案内单个计费项的报价明细。"""

    item_id: UUID
    kind: str
    label: str
    quantity: Decimal
    price_quantity: Decimal
    unit_amount: Decimal
    base_amount: Decimal
    fixed_price: Decimal | None
    multipliers: list[dict[str, object]]
    amount: Decimal
    details: dict[str, object]

    def to_snapshot(self) -> dict[str, object]:
        """转换为稳定的报价快照明细。"""

        return {
            "item_id": str(self.item_id),
            "kind": self.kind,
            "label": self.label,
            "quantity": str(self.quantity),
            "price_quantity": str(self.price_quantity),
            "unit_amount": str(self.unit_amount),
            "base_amount": str(self.base_amount),
            "fixed_price": None if self.fixed_price is None else str(self.fixed_price),
            "multipliers": list(self.multipliers),
            "amount": str(self.amount),
            "details": dict(self.details),
        }


@dataclass(frozen=True)
class PricingDecision:
    """方案选择与逐项报价的最终结果。"""

    amount: Decimal
    plan: PricingRule
    line_items: tuple[PricingLineItem, ...]
    snapshot: dict[str, object]


def quote_pricing(
    plans: Iterable[PricingRule],
    items_by_plan: Mapping[UUID, Iterable[PricingItem]],
    modifiers_by_plan: Mapping[UUID, Iterable[PricingModifier]],
    *,
    context: Mapping[str, object],
    facts: MaterialFacts,
    allowed_fields: list[str],
    group_ids: list[int] | None = None,
    created_at: datetime | None = None,
    group_multipliers: Mapping[int, Decimal] | None = None,
) -> PricingDecision:
    """选择首个命中方案并按计费项报价。

    参数为候选方案、方案计费项与修正项索引、标准化字段上下文、素材计量结果、条件白名单字段、
    用户可用令牌组、报价时间及各令牌分组的价格倍率。命中方案所属分组的倍率作用于全部计费项小计，
    得到最终金额。无命中方案或计量数量不合法时抛出 ``ValueError``。
    """

    group_ids = group_ids or []
    enriched_context: dict[str, object] = {
        **dict(context),
        "shanghai_time": _shanghai_time(created_at),
        "input_image_count": sum(facts.image_counts.values()),
        "input_video_seconds": sum(facts.video_seconds.values(), Decimal(0)),
    }
    allowed = set(allowed_fields)
    plan = _select_plan(plans, context=enriched_context, allowed_fields=allowed, group_ids=group_ids)
    plan_items = [item for item in items_by_plan.get(plan.id, []) if item.active]
    if not plan_items:
        raise ValueError("计费方案未配置任何启用计费项")
    plan_items.sort(key=lambda item: item.position)
    unit_amounts = {item.id: item.unit_amount for item in plan_items}
    modifiers = [modifier for modifier in modifiers_by_plan.get(plan.id, []) if modifier.active]
    modifiers.sort(key=lambda modifier: modifier.priority)
    line_items = tuple(
        _price_item(
            item,
            facts=facts,
            context=enriched_context,
            allowed_fields=allowed,
            modifiers=modifiers,
            unit_amounts=unit_amounts,
        )
        for item in plan_items
    )
    subtotal = sum((line.amount for line in line_items), Decimal(0)).quantize(
        _AMOUNT_PRECISION, rounding=ROUND_CEILING
    )
    group_multiplier = _resolve_group_multiplier(plan.token_group_id, group_multipliers)
    amount = (subtotal * group_multiplier).quantize(_AMOUNT_PRECISION, rounding=ROUND_CEILING)
    condition_evidence = _condition_evidence(plan.conditions, context=enriched_context, allowed_fields=allowed)
    snapshot = {
        "schema_version": _SNAPSHOT_SCHEMA_VERSION,
        "plan": {"id": str(plan.id), "name": plan.name, "conditions": condition_evidence},
        "material_facts": [dict(fact) for fact in facts.snapshot],
        "line_items": [line.to_snapshot() for line in line_items],
        "subtotal": str(subtotal),
        "group_multiplier": str(group_multiplier),
        "amount": str(amount),
        "currency": plan.currency,
    }
    return PricingDecision(amount=amount, plan=plan, line_items=line_items, snapshot=snapshot)


def select_pricing_plan(
    plans: Iterable[PricingRule],
    *,
    context: Mapping[str, object],
    allowed_fields: list[str],
    group_ids: list[int] | None = None,
    created_at: datetime | None = None,
) -> PricingRule:
    """只选择命中方案而不计算金额，供同步生成链路先确定计费模式。"""

    enriched_context: dict[str, object] = {
        **dict(context),
        "shanghai_time": _shanghai_time(created_at),
        "input_image_count": 0,
        "input_video_seconds": Decimal(0),
    }
    return _select_plan(plans, context=enriched_context, allowed_fields=set(allowed_fields), group_ids=group_ids or [])


def list_unpriced_groups(plans: Iterable[PricingRule], *, group_ids: Iterable[int]) -> list[int]:
    """列出没有任何启用计费方案的令牌分组，保持传入顺序并去重。

    渠道存在但选不出方案时，用它把「分组缺少启用定价规则」与「规则未命中本次请求条件」区分开。
    """

    priced = {plan.token_group_id for plan in plans if plan.active}
    missing: list[int] = []
    for group_id in group_ids:
        if group_id not in priced and group_id not in missing:
            missing.append(group_id)
    return missing


def missing_pricing_rule_message(*, model_name: str, group_ids: list[int]) -> str:
    """构造「模型在指定令牌分组缺少启用定价规则」的报错文案。"""

    groups = "、".join(f"“{group_id}”" for group_id in group_ids)
    return f"模型“{model_name}”在令牌分组{groups}没有启用的定价规则"


def effective_unit_amounts(
    items: Iterable[PricingItem],
    modifiers: Iterable[PricingModifier],
    *,
    context: Mapping[str, object],
    allowed_fields: list[str],
    created_at: datetime | None = None,
) -> dict[UUID, Decimal | None]:
    enriched_context: dict[str, object] = {**dict(context), "shanghai_time": _shanghai_time(created_at)}
    allowed = set(allowed_fields)
    active_modifiers = sorted(
        (modifier for modifier in modifiers if modifier.active), key=lambda modifier: modifier.priority
    )
    items_by_id = {item.id: item for item in items}
    amounts: dict[UUID, Decimal | None] = {}
    for item in items_by_id.values():
        _resolve_effective_unit_amount(
            item,
            items_by_id=items_by_id,
            amounts=amounts,
            modifiers=active_modifiers,
            context=enriched_context,
            allowed_fields=allowed,
        )
    return amounts


def _resolve_effective_unit_amount(
    item: PricingItem,
    *,
    items_by_id: Mapping[UUID, PricingItem],
    amounts: dict[UUID, Decimal | None],
    modifiers: list[PricingModifier],
    context: Mapping[str, object],
    allowed_fields: set[str],
) -> Decimal | None:
    """解析单个计费项的展示单价，输入视频时长项按 ``price_source_item_id`` 复用被引用项单价。"""

    if item.id in amounts:
        return amounts[item.id]
    source_id = item.price_source_item_id
    source = items_by_id.get(source_id) if source_id is not None else None
    base_amount = item.unit_amount
    if base_amount is None and source is not None:
        base_amount = _resolve_effective_unit_amount(
            source,
            items_by_id=items_by_id,
            amounts=amounts,
            modifiers=modifiers,
            context=context,
            allowed_fields=allowed_fields,
        )
    amount, fixed_price, _applied_multipliers = _apply_modifiers_to_amount(
        Decimal(0) if base_amount is None else Decimal(str(base_amount)),
        item,
        modifiers=modifiers,
        context=context,
        allowed_fields=allowed_fields,
    )
    resolved = None if base_amount is None and fixed_price is None else amount
    amounts[item.id] = resolved
    return resolved


def _select_plan(
    plans: Iterable[PricingRule],
    *,
    context: Mapping[str, object],
    allowed_fields: set[str],
    group_ids: list[int],
) -> PricingRule:
    candidates = [plan for plan in plans if plan.active and plan.token_group_id in group_ids]
    for plan in sorted(candidates, key=lambda item: item.priority):
        if _condition_matches(plan.conditions, context=context, allowed_fields=allowed_fields):
            return plan
    raise ValueError("未配置当前视频规格的有效计费方案")


def _price_item(
    item: PricingItem,
    *,
    facts: MaterialFacts,
    context: Mapping[str, object],
    allowed_fields: set[str],
    modifiers: list[PricingModifier],
    unit_amounts: Mapping[UUID, Decimal | None],
) -> PricingLineItem:
    quantity, price_quantity, details = _item_quantity(item, facts=facts, context=context, unit_amounts=unit_amounts)
    unit_amount = _item_unit_amount(item, unit_amounts=unit_amounts)
    base_amount = (price_quantity * unit_amount).quantize(_AMOUNT_PRECISION, rounding=ROUND_CEILING)
    amount, fixed_price, applied_multipliers = _apply_modifiers_to_amount(
        base_amount,
        item,
        modifiers=modifiers,
        context=context,
        allowed_fields=allowed_fields,
    )
    return PricingLineItem(
        item_id=item.id,
        kind=item.kind,
        label=item.label,
        quantity=quantity,
        price_quantity=price_quantity,
        unit_amount=unit_amount,
        base_amount=base_amount,
        fixed_price=fixed_price,
        multipliers=applied_multipliers,
        amount=amount,
        details=details,
    )


def _apply_modifiers_to_amount(
    base_amount: Decimal,
    item: PricingItem,
    *,
    modifiers: list[PricingModifier],
    context: Mapping[str, object],
    allowed_fields: set[str],
) -> tuple[Decimal, Decimal | None, list[dict[str, object]]]:
    amount = base_amount
    fixed_price: Decimal | None = None
    applied_multipliers: list[dict[str, object]] = []
    for modifier in _applicable_modifiers(item, modifiers=modifiers, context=context, allowed_fields=allowed_fields):
        if modifier.effect_type == "fixed_price" and fixed_price is None:
            fixed_price = _fixed_price(modifier)
            amount = fixed_price
            continue
        if modifier.effect_type == "multiplier":
            factor = _multiplier_factor(modifier)
            amount = amount * factor
            applied_multipliers.append(
                {"modifier_id": str(modifier.id), "priority": modifier.priority, "value": str(factor)}
            )
    return amount.quantize(_AMOUNT_PRECISION, rounding=ROUND_CEILING), fixed_price, applied_multipliers


def _resolve_group_multiplier(group_id: int, group_multipliers: Mapping[int, Decimal] | None) -> Decimal:
    """解析命中方案所属令牌分组的价格倍率，未提供或该分组缺省时按 1 处理。"""

    if not group_multipliers:
        return Decimal(1)
    value = group_multipliers.get(group_id)
    if value is None:
        return Decimal(1)
    try:
        factor = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("分组价格倍率不合法") from exc
    if not factor.is_finite() or factor <= 0:
        raise ValueError("分组价格倍率不合法")
    return factor


_INPUT_TEXT_KIND = PricingItemKind.input_text_tokens.value
_CACHE_WRITE_INPUT_TEXT_KIND = PricingItemKind.cache_write_input_text_tokens.value
_CACHED_INPUT_TEXT_KIND = PricingItemKind.cached_input_text_tokens.value
_OUTPUT_TEXT_KIND = PricingItemKind.output_text_tokens.value
_TEXT_TOKEN_KINDS = {_INPUT_TEXT_KIND, _CACHE_WRITE_INPUT_TEXT_KIND, _CACHED_INPUT_TEXT_KIND, _OUTPUT_TEXT_KIND}
_INPUT_IMAGE_TOKEN_KIND = PricingItemKind.input_image_tokens.value
_OUTPUT_IMAGE_TOKEN_KIND = PricingItemKind.output_image_tokens.value
_IMAGE_TOKEN_KINDS = {_INPUT_IMAGE_TOKEN_KIND, _OUTPUT_IMAGE_TOKEN_KIND}


def _text_token_quantity(kind: str, context: Mapping[str, object]) -> tuple[Decimal, str]:
    """按 kinds 语义解析 token 用量，缓存写入与缓存命中的输入 token 从全额输入中扣除。"""

    if kind == _CACHE_WRITE_INPUT_TEXT_KIND:
        return _sum_context_quantities(["cache_write_tokens"], context), "cache_write_tokens"
    if kind == _CACHED_INPUT_TEXT_KIND:
        return _sum_context_quantities(["cached_tokens"], context), "cached_tokens"
    if kind == _OUTPUT_TEXT_KIND:
        return _sum_context_quantities(["completion_tokens"], context), "completion_tokens"
    prompt = _sum_context_quantities(["prompt_tokens"], context)
    cached = _sum_context_quantities(["cached_tokens"], context)
    cache_write = _sum_context_quantities(["cache_write_tokens"], context)
    return max(prompt - cached - cache_write, Decimal(0)), "prompt_tokens"


def _item_quantity(
    item: PricingItem,
    *,
    facts: MaterialFacts,
    context: Mapping[str, object],
    unit_amounts: Mapping[UUID, Decimal | None],
) -> tuple[Decimal, Decimal, dict[str, object]]:
    if item.kind in {PricingItemKind.output_video_duration.value, PricingItemKind.output_image_count.value}:
        quantity = _sum_context_quantities(item.source_fields, context)
        return quantity, quantity, {"source_fields": list(item.source_fields)}
    if item.kind in _TEXT_TOKEN_KINDS:
        quantity, usage_field = _text_token_quantity(item.kind, context)
        return quantity, quantity / _TOKENS_PER_MILLION, {"usage_field": usage_field, "price_unit": "per_1m_tokens"}
    if item.kind in _IMAGE_TOKEN_KINDS:
        usage_field = "image_input_tokens" if item.kind == _INPUT_IMAGE_TOKEN_KIND else "image_output_tokens"
        quantity = _sum_context_quantities([usage_field], context)
        return (
            quantity,
            quantity / _TOKENS_PER_MILLION,
            {
                "usage_field": usage_field,
                "price_unit": "per_1m_tokens",
                "usage_source": context.get(f"{usage_field}_source", "upstream"),
            },
        )
    if item.kind == PricingItemKind.request_fixed.value:
        return Decimal(1), Decimal(1), {}
    if item.kind == PricingItemKind.input_video_duration.value:
        quantity = sum(
            (facts.video_seconds.get(field_name, Decimal(0)) for field_name in item.source_fields), Decimal(0)
        )
        details: dict[str, object] = {"source_fields": list(item.source_fields), "measured_seconds": str(quantity)}
        if item.price_source_item_id is not None:
            details["price_source_item_id"] = str(item.price_source_item_id)
        return quantity, quantity, details
    if item.kind == PricingItemKind.input_image_fixed.value:
        total = sum(facts.image_counts.get(field_name, 0) for field_name in item.source_fields)
        chargeable = max(total - item.free_quantity, 0)
        return (
            Decimal(total),
            Decimal(chargeable),
            {
                "source_fields": list(item.source_fields),
                "image_quantity": total,
                "free_quantity": item.free_quantity,
                "chargeable_quantity": chargeable,
            },
        )
    if item.kind == PricingItemKind.input_material_tokens.value:
        quantity = _material_token_quantity(item, facts=facts, context=context)
        chargeable = max(quantity - Decimal(item.free_quantity), Decimal(0))
        return (
            quantity,
            chargeable / Decimal(1000),
            {
                "source_fields": list(item.source_fields),
                "material_tokens": str(quantity),
                "free_quantity": item.free_quantity,
                "chargeable_tokens": str(chargeable),
                "price_unit": "per_1k_tokens",
            },
        )
    raise ValueError("计费项类型不受支持")


def _item_unit_amount(item: PricingItem, *, unit_amounts: Mapping[UUID, Decimal | None]) -> Decimal:
    source_id = item.price_source_item_id
    amount = unit_amounts.get(source_id) if source_id is not None else item.unit_amount
    if amount is None:
        raise ValueError("该模型未配置定价")
    if not isinstance(amount, Decimal):
        amount = Decimal(str(amount))
    if not amount.is_finite() or amount < 0:
        raise ValueError("计费项基础单价不合法")
    return amount


def _sum_context_quantities(source_fields: list[str], context: Mapping[str, object]) -> Decimal:
    total = Decimal(0)
    for field_name in source_fields:
        value = context.get(field_name)
        if isinstance(value, bool) or not isinstance(value, int | float | Decimal):
            raise ValidationError(
                f"计费项缺少合法的 {field_name} 数量字段",
                code="pricing.missing_quantity_field",
                params={"name": field_name},
            )
        quantity = Decimal(str(value))
        if not quantity.is_finite() or quantity < 0:
            raise ValidationError(
                f"计费项缺少合法的 {field_name} 数量字段",
                code="pricing.missing_quantity_field",
                params={"name": field_name},
            )
        total += quantity
    return total


def _material_token_quantity(item: PricingItem, *, facts: MaterialFacts, context: Mapping[str, object]) -> Decimal:
    resolution = context.get("resolution")
    if resolution == "480P":
        video_factor = Decimal("2886")
    elif resolution in {"768P", "1080P"}:
        # 1080P 的涨价由档位素材单价翻倍承担，token 系数与 768P 一致，素材费用正好为 768P 的两倍。
        video_factor = Decimal("7459.2")
    else:
        video_factor = Decimal(0)
    image_tokens = sum((facts.image_tokens.get(field, Decimal(0)) for field in item.source_fields), Decimal(0))
    video_seconds = sum((facts.video_seconds.get(field, Decimal(0)) for field in item.source_fields), Decimal(0))
    audio_seconds = sum((facts.audio_seconds.get(field, Decimal(0)) for field in item.source_fields), Decimal(0))
    return image_tokens + video_seconds * video_factor + audio_seconds * Decimal("80")


def chargeable_material_tokens(snapshot: object) -> Decimal | None:
    """从报价快照提取素材计费项扣除免费额度后的可计费 token 数。

    参数为一次报价的 ``snapshot`` 字典；快照不含素材计费项、结构不完整或数值无法解析时返回 ``None``，
    不抛出异常。返回值供应用层在接口响应中回显素材 token 用量。
    """

    if not isinstance(snapshot, Mapping):
        return None
    line_items = snapshot.get("line_items")
    if not isinstance(line_items, list):
        return None
    for line in line_items:
        if not isinstance(line, Mapping) or line.get("kind") != PricingItemKind.input_material_tokens.value:
            continue
        details = line.get("details")
        value = details.get("chargeable_tokens") if isinstance(details, Mapping) else None
        if not isinstance(value, str):
            return None
        try:
            return Decimal(value)
        except InvalidOperation:
            return None
    return None


def _material_token_total(facts: MaterialFacts, *, resolution: object) -> Decimal:
    if resolution == "480P":
        video_factor = Decimal("2886")
    elif resolution in {"768P", "1080P"}:
        video_factor = Decimal("7459.2")
    else:
        video_factor = Decimal(0)
    return (
        sum(facts.image_tokens.values(), Decimal(0))
        + sum(facts.video_seconds.values(), Decimal(0)) * video_factor
        + sum(facts.audio_seconds.values(), Decimal(0)) * Decimal("80")
    )


def _applicable_modifiers(
    item: PricingItem,
    *,
    modifiers: list[PricingModifier],
    context: Mapping[str, object],
    allowed_fields: set[str],
) -> list[PricingModifier]:
    return [
        modifier
        for modifier in modifiers
        if _scope_covers(modifier, item)
        and _condition_matches(modifier.conditions, context=context, allowed_fields=allowed_fields)
    ]


def _scope_covers(modifier: PricingModifier, item: PricingItem) -> bool:
    if modifier.scope_type == "all_items":
        return True
    if modifier.scope_type == "item_kind":
        return item.kind in set(modifier.scope_item_kinds)
    if modifier.scope_type == "item_ids":
        return str(item.id) in set(modifier.scope_item_ids)
    raise ValueError("价格修正作用范围不受支持")


def _fixed_price(modifier: PricingModifier) -> Decimal:
    try:
        amount = Decimal(str(modifier.effect_payload.get("amount")))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("固定价格修正参数不合法") from exc
    if not amount.is_finite() or amount < 0:
        raise ValueError("固定价格修正参数不合法")
    return amount


def _multiplier_factor(modifier: PricingModifier) -> Decimal:
    try:
        factor = Decimal(str(modifier.effect_payload.get("factor")))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("价格倍率不合法") from exc
    if not factor.is_finite() or factor < 0:
        raise ValueError("价格倍率不合法")
    return factor


def _condition_matches(
    conditions: list[dict[str, Any]], *, context: Mapping[str, object], allowed_fields: set[str]
) -> bool:
    for condition in conditions:
        field_name = condition.get("field")
        operator = condition.get("operator")
        expected = condition.get("value")
        if not isinstance(field_name, str) or field_name not in allowed_fields | _INTERNAL_PRICING_FIELDS:
            raise ValueError("价格规则引用了未授权字段")
        if operator not in _OPERATORS:
            raise ValueError("价格规则操作符不受支持")
        if field_name not in context or not _compare(context[field_name], str(operator), expected, field_name):
            return False
    return True


def _condition_evidence(
    conditions: list[dict[str, Any]], *, context: Mapping[str, object], allowed_fields: set[str]
) -> list[dict[str, object]]:
    evidence: list[dict[str, object]] = []
    for condition in conditions:
        field_name = condition.get("field")
        operator = condition.get("operator")
        expected = condition.get("value")
        if not isinstance(field_name, str) or field_name not in allowed_fields | _INTERNAL_PRICING_FIELDS:
            raise ValueError("价格规则引用了未授权字段")
        actual = context.get(field_name)
        evidence.append(
            {
                "field": field_name,
                "actual": None if actual is None else str(actual),
                "operator": operator,
                "expected": expected,
                "matched": field_name in context and _compare(actual, str(operator), expected, field_name),
            }
        )
    return evidence


def _shanghai_time(created_at: datetime | None) -> str:
    if created_at is None:
        timestamp = datetime.now(UTC)
    elif isinstance(created_at, datetime):
        timestamp = created_at.replace(tzinfo=UTC) if created_at.tzinfo is None else created_at
    else:
        raise ValueError("报价时间不合法")
    return timestamp.astimezone(_SHANGHAI_TIMEZONE).time().isoformat(timespec="microseconds")


def _compare(actual: object, operator: str, expected: object, field_name: str | None = None) -> bool:
    if operator == "eq":
        return actual == expected
    if operator == "in":
        if not isinstance(expected, list):
            raise ValueError("in 操作符必须使用数组值")
        return actual in expected
    if operator == "gte":
        return actual >= expected
    if operator == "lte":
        return actual <= expected
    if not isinstance(expected, list) or len(expected) != 2:
        raise ValueError("between 操作符必须使用两个边界值")
    if field_name == "shanghai_time":
        if not isinstance(actual, str) or any(not isinstance(value, str) for value in expected):
            raise ValueError("上海时间条件不合法")
        try:
            actual_time = time.fromisoformat(actual)
            start, end = (time.fromisoformat(value) for value in expected)
        except ValueError as exc:
            raise ValueError("上海时间条件不合法") from exc
        return start <= actual_time <= end if start <= end else actual_time >= start or actual_time <= end
    return expected[0] <= actual <= expected[1]
