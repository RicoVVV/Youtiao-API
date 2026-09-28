"""模型渠道与计费方案发布前的纯校验服务。

本模块集中验证不可由单表约束表达的配置边界，不写入数据库；发布用例应在同一事务内先调用本服务，
再持久化整个配置版本，从而避免半成品版本对新任务可见。
"""

from collections.abc import Iterable
from datetime import time
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from app.core.errors import ValidationError
from app.modules.channels.application.configuration import validate_standardized_projection
from app.modules.models.model import ModelRoute
from app.modules.pricing.model.pricing import PricingModifier, PricingRule
from app.modules.pricing.model.pricing_item import PricingItem, PricingItemKind

_SUPPORTED_FIELD_TYPES = {"string", "integer", "number", "boolean", "array", "object"}
_INTERNAL_PRICING_FIELDS = {
    "shanghai_time",
    "input_image_count",
    "input_video_seconds",
    "image_pixel_count",
    "prompt_tokens",
    "cache_write_tokens",
    "cached_tokens",
    "completion_tokens",
}
_INTERNAL_PRICING_FIELD_TYPES = {
    "shanghai_time": "string",
    "input_image_count": "integer",
    "input_video_seconds": "number",
    "image_pixel_count": "integer",
    "prompt_tokens": "integer",
    "cache_write_tokens": "integer",
    "cached_tokens": "integer",
    "completion_tokens": "integer",
}
_OPERATORS = {"eq", "in", "gte", "lte", "between"}
_EFFECT_TYPES = {"multiplier", "fixed_price"}
_SCOPE_TYPES = {"item_ids", "item_kind", "all_items"}
_ITEM_KINDS = {kind.value for kind in PricingItemKind}
_OUTPUT_KIND = PricingItemKind.output_video_duration.value
_INPUT_VIDEO_KIND = PricingItemKind.input_video_duration.value
_INPUT_IMAGE_KIND = PricingItemKind.input_image_fixed.value
_INPUT_MATERIAL_TOKENS_KIND = PricingItemKind.input_material_tokens.value
_OUTPUT_IMAGE_KIND = PricingItemKind.output_image_count.value
_TEXT_TOKEN_KINDS = {
    PricingItemKind.input_text_tokens.value,
    PricingItemKind.cache_write_input_text_tokens.value,
    PricingItemKind.cached_input_text_tokens.value,
    PricingItemKind.output_text_tokens.value,
}
_IMAGE_TOKEN_KINDS = {
    PricingItemKind.input_image_tokens.value,
    PricingItemKind.output_image_tokens.value,
}
_REQUEST_FIXED_KIND = PricingItemKind.request_fixed.value
_ZERO_FORBIDDEN_KINDS = {_OUTPUT_KIND, _INPUT_VIDEO_KIND}
_COUNT_KINDS = {_OUTPUT_KIND, _OUTPUT_IMAGE_KIND}
_SOURCE_FIELDS_OPTIONAL_KINDS = _TEXT_TOKEN_KINDS | _IMAGE_TOKEN_KINDS | {_REQUEST_FIXED_KIND}
_REQUIRED_OUTPUT_KINDS_BY_MODEL_TYPE = {
    "video": {_OUTPUT_KIND},
    "image": {_OUTPUT_IMAGE_KIND, _REQUEST_FIXED_KIND, *_IMAGE_TOKEN_KINDS},
    "text": _TEXT_TOKEN_KINDS | {_REQUEST_FIXED_KIND},
}


def _declares_supported_type(rule: dict[str, Any]) -> bool:
    """判断字段规则声明的类型是否受支持。

    规则省略 ``type`` 表示该字段接受任意 JSON 类型；声明了 ``type`` 时必须是受支持的基础类型。
    """

    return "type" not in rule or (isinstance(rule["type"], str) and rule["type"] in _SUPPORTED_FIELD_TYPES)


def validate_configuration(
    *,
    channels: Iterable[ModelRoute],
    rules: Iterable[PricingRule],
    modifiers: Iterable[PricingModifier],
    items: Iterable[PricingItem] = (),
    allowed_fields: list[str],
    input_schema: dict[str, Any] | None = None,
    standardized_projection: dict[str, Any] | None = None,
    material_fields: dict[str, Any] | None = None,
    derived_pricing_fields: list[dict[str, Any]] | None = None,
    model_type: str = "video",
) -> None:
    """校验一份待发布模型配置的排序、计费项、修正项和映射约束。

    任何校验失败均抛出 ``ValueError``；调用方不得提交已插入的部分配置，确保发布是原子的。
    ``model_type`` 决定计费方案必须包含的计费主体项类别。
    """

    channel_list = list(channels)
    rule_list = list(rules)
    modifier_list = list(modifiers)
    item_list = list(items)
    _validate_model_contract(
        allowed_fields=allowed_fields,
        input_schema=input_schema,
        standardized_projection=standardized_projection,
        derived_pricing_fields=derived_pricing_fields,
    )
    field_types = _pricing_field_types(
        input_schema=input_schema,
        standardized_projection=standardized_projection,
    )
    _validate_grouped_positions(
        rule_list, lambda item: (item.model_id, item.token_group_id), lambda item: item.priority, "价格规则"
    )
    for route in channel_list:
        if route.weight <= 0:
            raise ValueError("渠道权重必须为正整数")
    for rule in rule_list:
        _validate_conditions(rule.conditions, allowed_fields=allowed_fields, field_types=field_types)
    rules_by_id = {rule.id: rule for rule in rule_list}
    _validate_items(
        item_list,
        rules=rules_by_id,
        allowed_fields=allowed_fields,
        material_fields=material_fields or {},
        field_types=field_types,
        model_type=model_type,
    )
    _validate_grouped_positions(
        modifier_list, lambda item: item.pricing_rule_id, lambda item: item.priority, "价格修正规则"
    )
    for modifier in modifier_list:
        if modifier.effect_type not in _EFFECT_TYPES:
            raise ValueError("价格修正类型不受支持")
        if modifier.pricing_rule_id not in rules_by_id:
            raise ValueError("价格修正必须属于同一批保存的计费方案")
        _validate_conditions(modifier.conditions, allowed_fields=allowed_fields, field_types=field_types)
        _validate_modifier_payload(modifier)
        _validate_modifier_scope(modifier, plan_items=_items_of(item_list, modifier.pricing_rule_id))


def _validate_model_contract(
    *,
    allowed_fields: list[str],
    input_schema: dict[str, Any] | None,
    standardized_projection: dict[str, Any] | None,
    derived_pricing_fields: list[dict[str, Any]] | None,
) -> None:
    """验证字段契约结构及价格白名单只引用其公开字段。"""

    if len(allowed_fields) != len(set(allowed_fields)):
        raise ValueError("价格字段白名单不能重复")
    if any(not isinstance(field, str) or not field.isidentifier() for field in allowed_fields):
        raise ValueError("价格字段白名单不合法")
    if input_schema is None:
        if allowed_fields:
            raise ValueError("价格字段白名单只能引用模型请求契约或标准化投影字段")
        if derived_pricing_fields:
            raise ValueError("派生计费字段只能引用模型请求契约")
        return
    if input_schema.get("type") != "object" or not isinstance(input_schema.get("properties"), dict):
        raise ValueError("公开模型字段契约不合法")
    validate_standardized_projection(input_schema, standardized_projection or {})
    properties = input_schema["properties"]
    if any(not isinstance(rule, dict) or not _declares_supported_type(rule) for rule in properties.values()):
        raise ValueError("公开模型字段契约不合法")
    projected_fields = set(standardized_projection or {})
    if any(field not in properties and field not in projected_fields for field in allowed_fields):
        raise ValueError("价格字段白名单引用了未声明字段")
    _validate_derived_pricing_fields(derived_pricing_fields, properties)


def _validate_derived_pricing_fields(
    derived_pricing_fields: list[dict[str, Any]] | None, properties: dict[str, Any]
) -> None:
    if derived_pricing_fields is None:
        return
    if not isinstance(derived_pricing_fields, list):
        raise ValueError("派生计费字段声明不合法")
    seen_types: set[str] = set()
    for declaration in derived_pricing_fields:
        if not isinstance(declaration, dict) or set(declaration) != {"type", "size_source"}:
            raise ValueError("派生计费字段声明不合法")
        if declaration["type"] != "image_pixel_count":
            raise ValueError("派生计费字段类型不受支持")
        if declaration["type"] in seen_types:
            raise ValueError("派生计费字段类型不能重复")
        seen_types.add(declaration["type"])
        size_source = declaration["size_source"]
        source_rule = properties.get(size_source) if isinstance(size_source, str) else None
        if not isinstance(source_rule, dict) or source_rule.get("type") != "string":
            raise ValueError("图片像素派生字段必须引用声明的字符串字段")


def _pricing_field_types(
    *, input_schema: dict[str, Any] | None, standardized_projection: dict[str, Any] | None
) -> dict[str, str]:
    if input_schema is None:
        return dict(_INTERNAL_PRICING_FIELD_TYPES)
    properties = input_schema["properties"]
    field_types = {
        field: rule["type"] for field, rule in properties.items() if rule.get("type") in _SUPPORTED_FIELD_TYPES
    }
    for target, rule in (standardized_projection or {}).items():
        field_types[target] = properties[rule["source"]]["type"]
    return {**field_types, **_INTERNAL_PRICING_FIELD_TYPES}


def _validate_condition_value(condition: dict[str, Any], *, field_types: dict[str, str]) -> None:
    """校验价格比较值的容器形状，并在有字段契约时验证基本值类型。"""

    operator = condition["operator"]
    value = condition.get("value")
    if operator == "in" and not isinstance(value, list):
        raise ValueError("in 操作符必须使用数组值")
    if operator == "between" and (not isinstance(value, list) or len(value) != 2):
        raise ValueError("between 操作符必须使用两个边界值")
    field = condition["field"]
    if field == "shanghai_time":
        if operator != "between":
            raise ValueError("上海时间条件仅支持 between 操作符")
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise ValueError("上海时间条件必须使用两个时间边界值")
        try:
            for item in value:
                time.fromisoformat(item)
        except ValueError as exc:
            raise ValueError("上海时间条件必须使用 HH:MM:SS.ffffff 格式") from exc
        if any(len(item) != 15 or item[2] != ":" or item[5] != ":" or item[8] != "." for item in value):
            raise ValueError("上海时间条件必须使用 HH:MM:SS.ffffff 格式")
        return
    field_type = field_types.get(field)
    if field_type is None:
        return
    values = value if operator in {"in", "between"} else [value]
    if any(not _matches_contract_type(item, field_type) for item in values):
        raise ValueError("价格规则比较值类型与模型字段契约不一致")


def _matches_contract_type(value: Any, field_type: str) -> bool:
    """判断价格规则静态比较值是否符合公开字段的 JSON 基础类型。"""

    return {
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, int | float) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "array": isinstance(value, list),
        "object": isinstance(value, dict),
    }[field_type]


def _validate_positions(items: list[Any], position_getter: Any, label: str) -> None:
    """验证单一父对象范围内的位置值唯一。"""

    positions = [position_getter(item) for item in items]
    if len(positions) != len(set(positions)):
        raise ValidationError(
            f"{label} position 不能重复", code="pricing_plan.duplicate_position", params={"label": label}
        )


def _validate_grouped_positions(items: list[Any], parent_getter: Any, position_getter: Any, label: str) -> None:
    """验证按父对象分组后的位置值唯一。"""

    grouped: dict[object, list[Any]] = {}
    for item in items:
        grouped.setdefault(parent_getter(item), []).append(item)
    for group in grouped.values():
        _validate_positions(group, position_getter, label)


def _validate_conditions(
    conditions: list[dict[str, Any]], *, allowed_fields: list[str], field_types: dict[str, str]
) -> None:
    for condition in conditions:
        if condition.get("field") not in set(allowed_fields) | _INTERNAL_PRICING_FIELDS:
            raise ValueError("价格规则引用了未授权字段")
        if condition.get("operator") not in _OPERATORS:
            raise ValueError("价格规则操作符不受支持")
        _validate_condition_value(condition, field_types=field_types)


def _items_of(items: list[PricingItem], pricing_rule_id: UUID) -> list[PricingItem]:
    """返回指定方案下的全部计费项。"""

    return [item for item in items if item.pricing_rule_id == pricing_rule_id]


def _validate_items(
    items: list[PricingItem],
    *,
    rules: dict[UUID, PricingRule],
    allowed_fields: list[str],
    material_fields: dict[str, Any],
    field_types: dict[str, str],
    model_type: str,
) -> None:
    """校验计费项类型、计量来源字段、单价来源与方案完整性。"""

    required_kinds = _REQUIRED_OUTPUT_KINDS_BY_MODEL_TYPE.get(model_type)
    if required_kinds is None:
        raise ValueError("模型类型不支持计费校验")
    _validate_grouped_positions(items, lambda item: item.pricing_rule_id, lambda item: item.position, "计费项")
    for item in items:
        if item.pricing_rule_id not in rules:
            raise ValueError("计费项必须属于同一批保存的计费方案")
        _validate_item(
            item,
            plan_items=_items_of(items, item.pricing_rule_id),
            allowed_fields=allowed_fields,
            material_fields=material_fields,
            field_types=field_types,
        )
    for rule in rules.values():
        if not rule.active:
            continue
        if not any(item.active and item.kind in required_kinds for item in _items_of(items, rule.id)):
            raise ValueError("计费方案至少需要一个启用的计费主体项")
        if model_type == "image":
            _validate_image_pricing_mode(_items_of(items, rule.id))


def _validate_item(
    item: PricingItem,
    *,
    plan_items: list[PricingItem],
    allowed_fields: list[str],
    material_fields: dict[str, Any],
    field_types: dict[str, str],
) -> None:
    """校验单个计费项的类别、计量来源和基础单价。"""

    if item.kind not in _ITEM_KINDS:
        raise ValueError("计费项类型不受支持")
    if not isinstance(item.label, str) or not item.label:
        raise ValueError("计费项名称不合法")
    source_allowed_fields = list(allowed_fields)
    if item.kind == _INPUT_MATERIAL_TOKENS_KIND:
        source_allowed_fields.extend(field for field in material_fields if field not in source_allowed_fields)
    _validate_source_fields(
        item.source_fields,
        allowed_fields=source_allowed_fields,
        required=item.kind not in _SOURCE_FIELDS_OPTIONAL_KINDS,
    )
    if item.kind in _COUNT_KINDS and any(
        field_types.get(field) not in {"integer", "number"} for field in item.source_fields
    ):
        raise ValueError("按数量计费项必须引用数值类型字段")
    if item.kind == _INPUT_VIDEO_KIND:
        _validate_material_source_fields(item.source_fields, material_fields, category="video")
    if item.kind == _INPUT_IMAGE_KIND:
        _validate_material_source_fields(item.source_fields, material_fields, category="image")
    if item.kind == _INPUT_MATERIAL_TOKENS_KIND:
        _validate_material_token_source_fields(item.source_fields, material_fields)
    if not isinstance(item.free_quantity, int) or isinstance(item.free_quantity, bool) or item.free_quantity < 0:
        raise ValueError("计费项免费数量必须为非负整数")
    _validate_estimate_config(item)
    if item.kind == _INPUT_VIDEO_KIND and item.price_source_item_id is not None:
        _validate_price_source(item, plan_items)
        return
    if item.price_source_item_id is not None:
        raise ValueError("仅输入视频时长计费项可以引用其他计费项单价")
    _validate_unit_amount(item.unit_amount, allow_zero=item.kind not in _ZERO_FORBIDDEN_KINDS)


def _validate_image_pricing_mode(items: list[PricingItem]) -> None:
    active_kinds = {item.kind for item in items if item.active}
    image_token_kinds = active_kinds & _IMAGE_TOKEN_KINDS
    count_kinds = active_kinds & {_OUTPUT_IMAGE_KIND, _REQUEST_FIXED_KIND}
    if image_token_kinds and count_kinds:
        raise ValueError("图片计费不能混用按次按张与图片 Token 计费项")
    if image_token_kinds and image_token_kinds != _IMAGE_TOKEN_KINDS:
        raise ValueError("图片 Token 计费必须同时配置图片输入与输出 Token 项")


def _validate_estimate_config(item: PricingItem) -> None:
    config = getattr(item, "estimate_config", {})
    if not isinstance(config, dict):
        raise ValueError("图片 Token 估算配置不合法")
    if item.kind not in _IMAGE_TOKEN_KINDS:
        if config:
            raise ValueError("仅图片 Token 计费项可以配置估算参数")
        return
    allowed = {
        "text_chars_per_token",
        "input_image_tokens_per_image",
        "output_image_tokens_per_image",
        "gemini_unknown_image_tiles_per_image",
    }
    if set(config) - allowed:
        raise ValueError("图片 Token 估算配置包含未授权字段")
    expected = (
        "input_image_tokens_per_image"
        if item.kind == PricingItemKind.input_image_tokens.value
        else "output_image_tokens_per_image"
    )
    if expected not in config:
        raise ValueError("图片 Token 计费项缺少每张图片 Token 估算参数")
    if item.kind == PricingItemKind.input_image_tokens.value and "text_chars_per_token" not in config:
        raise ValueError("图片输入 Token 计费项缺少文本字符 Token 比率")
    if item.kind == PricingItemKind.input_image_tokens.value and "gemini_unknown_image_tiles_per_image" not in config:
        raise ValueError("图片输入 Token 计费项缺少 Gemini 未知尺寸图片 tile 数")
    for value in config.values():
        try:
            decimal = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValueError("图片 Token 估算配置不合法") from exc
        if not decimal.is_finite() or decimal <= 0:
            raise ValueError("图片 Token 估算配置必须为正数")


def _validate_source_fields(source_fields: Any, *, allowed_fields: list[str], required: bool = True) -> None:
    """校验计量来源字段不重复且位于价格字段白名单内，按需允许为空。"""

    if not isinstance(source_fields, list):
        raise ValueError("计费项计量来源字段不合法")
    if required and not source_fields:
        raise ValueError("计费项必须声明计量来源字段")
    if len(source_fields) != len(set(source_fields)):
        raise ValueError("计费项计量来源字段不能重复")
    allowed = set(allowed_fields)
    if any(not isinstance(field, str) or field not in allowed for field in source_fields):
        raise ValueError("计费项计量来源字段未在价格字段白名单中声明")


def _validate_material_source_fields(
    source_fields: list[str], material_fields: dict[str, Any], *, category: str
) -> None:
    for field_name in source_fields:
        declaration = material_fields.get(field_name)
        categories = declaration.get("categories") if isinstance(declaration, dict) else None
        if not isinstance(categories, list) or category not in categories:
            raise ValidationError(
                f"计费项计量来源字段不支持{category}素材",
                code="pricing_plan.material_field_unsupported_kind",
                params={"category": category},
            )


def _validate_material_token_source_fields(source_fields: list[str], material_fields: dict[str, Any]) -> None:
    for field_name in source_fields:
        declaration = material_fields.get(field_name)
        categories = declaration.get("categories") if isinstance(declaration, dict) else None
        if not isinstance(categories, list) or not set(categories) & {"image", "video", "audio"}:
            raise ValueError("素材 Token 计费项必须引用素材字段")


def _validate_unit_amount(unit_amount: Any, *, allow_zero: bool) -> None:
    """校验基础单价为非负有限 Decimal，输出与输入视频项目不允许为零。

    留空（``None``）表示尚未定价，直接放行：视频模板的默认定价项按采购价留空，
    由管理员创建模型后在定价面板补填；未补填前发起生成会在结算时被拦下。
    """

    if unit_amount is None:
        return
    try:
        amount = Decimal(str(unit_amount))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("计费项单价不合法") from exc
    if not amount.is_finite() or amount < 0 or (amount == 0 and not allow_zero):
        raise ValueError("计费项单价不合法")


def _validate_price_source(item: PricingItem, plan_items: list[PricingItem]) -> None:
    """校验输入视频项目只引用同方案唯一的启用输出视频时长项目。"""

    targets = [candidate for candidate in plan_items if candidate.id == item.price_source_item_id]
    if len(targets) != 1 or targets[0].kind != _OUTPUT_KIND:
        raise ValueError("输入视频计费项必须引用同方案唯一的输出视频时长计费项")
    if item.active and not targets[0].active:
        raise ValueError("输入视频计费项不能引用已停用的输出视频时长计费项")


def _validate_modifier_payload(modifier: PricingModifier) -> None:
    """校验修正项效果参数：倍率为非负有限值，固定价格为非负有限值。"""

    try:
        if modifier.effect_type == "multiplier":
            factor = Decimal(str(modifier.effect_payload.get("factor")))
            if not factor.is_finite() or factor < 0:
                raise ValueError
        else:
            amount = Decimal(str(modifier.effect_payload.get("amount")))
            if not amount.is_finite() or amount < 0:
                raise ValueError
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("价格修正参数不合法") from exc


def _validate_modifier_scope(modifier: PricingModifier, *, plan_items: list[PricingItem]) -> None:
    """校验修正项作用范围非空、不跨方案，且固定价格只作用于一个计费项。"""

    scope_type = modifier.scope_type
    if scope_type not in _SCOPE_TYPES:
        raise ValueError("价格修正作用范围不受支持")
    item_ids = modifier.scope_item_ids
    item_kinds = modifier.scope_item_kinds
    if not isinstance(item_ids, list) or not isinstance(item_kinds, list):
        raise ValueError("价格修正作用范围不合法")
    if scope_type == "all_items":
        if item_ids or item_kinds:
            raise ValueError("作用于全部计费项时不能指定具体计费项")
    elif scope_type == "item_kind":
        if not item_kinds or item_ids:
            raise ValueError("价格修正必须指定有效的计费项类别")
        if any(kind not in _ITEM_KINDS for kind in item_kinds):
            raise ValueError("价格修正引用了不受支持的计费项类别")
    else:
        if not item_ids or item_kinds:
            raise ValueError("价格修正必须指定有效的计费项")
        plan_ids = {str(item.id) for item in plan_items}
        if any(not isinstance(item_id, str) or item_id not in plan_ids for item_id in item_ids):
            raise ValueError("价格修正引用了其他方案的计费项")
    if modifier.effect_type == "fixed_price" and (scope_type != "item_ids" or len(set(item_ids)) != 1):
        raise ValueError("固定价格修正必须且只能作用于一个计费项")
