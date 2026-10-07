"""公开视频模型请求解析用例。

本模块根据当前公开模型版本校验通用视频请求，并生成供渠道映射、报价和任务冻结的标准字段；
不写入数据库、不调用上游服务，也不处理 HTTP 异常转换。
"""

import json
from dataclasses import dataclass
from typing import Any

from sqlmodel import Session

from app.core.errors import ValidationError
from app.modules.channels.crud.channels import ChannelCrud
from app.modules.models.model import Model

_STANDARDIZED_FIELD_TYPES = {
    "prompt": "string",
    "duration_seconds": "integer",
    "resolution": "string",
    "workflow_id": "string",
    "normalized_resolution": "string",
    "aspect_ratio": "string",
}


@dataclass(frozen=True)
class NormalizedVideoRequest:
    """保存公开模型校验后的标准请求和计费定位信息。"""

    workflow_id: str | None
    normalized_resolution: str | None
    duration_seconds: int | None
    standardized_fields: dict[str, Any]
    provider_request: dict[str, Any]


@dataclass(frozen=True)
class ResolvedVideoModel:
    """保存公开模型解析后的标准化请求与可冻结配置引用。"""

    model_name: str
    normalized_request: NormalizedVideoRequest
    model_config: Model


def resolve_video_model(session: Session, payload: dict[str, Any]) -> ResolvedVideoModel:
    """解析公开模型请求并生成渠道映射和计价使用的标准字段。

    参数 ``payload`` 必须携带公开模型标识。模型不存在、未启用或请求字段不合法时抛出 ``ValueError``；
    返回值包含唯一的当前生效模型版本及独立请求快照。
    """

    requested_model = payload.get("model")
    if not isinstance(requested_model, str):
        raise ValueError("model 必须是字符串")
    config = ChannelCrud(session).get_active_model(name=requested_model, model_type="video")
    if config is None:
        raise ValueError("未配置当前公开模型")
    contract = config.input_contract
    if not isinstance(contract, dict):
        raise ValueError("视频模型缺少请求契约")
    input_schema = contract.get("input_schema")
    projection_rules = contract.get("projection")
    if not isinstance(input_schema, dict) or not isinstance(projection_rules, dict):
        raise ValueError("视频模型请求契约不合法")
    normalized_payload = _normalize_input_payload(payload, input_schema)
    _validate_input_contract(normalized_payload, input_schema)
    projection = _project_standardized_fields(normalized_payload, input_schema, projection_rules)
    normalized = NormalizedVideoRequest(
        workflow_id=projection["workflow_id"],
        normalized_resolution=projection["normalized_resolution"],
        duration_seconds=projection["duration_seconds"],
        standardized_fields=projection,
        provider_request=dict(normalized_payload),
    )
    return ResolvedVideoModel(model_name=requested_model, normalized_request=normalized, model_config=config)


def _normalize_input_payload(payload: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        raise ValueError("公开模型字段契约不合法")
    normalized = dict(payload)
    for field, value in payload.items():
        if field == "model" or field not in properties:
            continue
        rule = properties[field]
        if not isinstance(rule, dict):
            continue
        normalized[field] = _normalize_field_value(field, value, rule.get("type"))
    return normalized


def _normalize_field_value(field: str, value: Any, field_type: object) -> Any:
    if not isinstance(field_type, str) or not isinstance(value, str | list):
        return value
    if field_type == "array":
        if isinstance(value, list):
            return value
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return [value]
        return parsed if isinstance(parsed, list) else value
    if isinstance(value, list):
        return value
    if field_type == "string":
        return value
    if field_type == "boolean" and value.lower() in {"true", "false"}:
        return value.lower() == "true"
    if field_type == "integer":
        try:
            return int(value)
        except ValueError:
            return value
    if field_type == "number":
        try:
            return float(value)
        except ValueError:
            return value
    if field_type == "object":
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def validate_standardized_projection(input_schema: dict[str, Any], projection: dict[str, Any]) -> None:
    """校验模型配置声明的任务标准字段投影规则。

    投影目标只能是平台任务和计价使用的标准字段，来源必须已在模型 ``input_schema`` 中声明；``values``
    仅用于把来源枚举归一为标准值。规则不合法时抛出 ``ValueError``，不写入数据库。
    """

    if not isinstance(projection, dict):
        raise ValueError("模型标准化投影不合法")
    properties = input_schema.get("properties")
    if not isinstance(properties, dict):
        raise ValueError("公开模型字段契约不合法")
    for target, rule in projection.items():
        if target not in _STANDARDIZED_FIELD_TYPES or not isinstance(rule, dict):
            raise ValueError("模型标准化投影不合法")
        source = rule.get("source")
        if not isinstance(source, str) or source not in properties:
            raise ValueError("模型标准化投影引用了未声明字段")
        if properties[source].get("type") != _STANDARDIZED_FIELD_TYPES[target]:
            raise ValueError("模型标准化投影字段类型不一致")
        values = rule.get("values")
        if values is not None and (
            not isinstance(values, dict) or not all(isinstance(value, str) for value in values.values())
        ):
            raise ValueError("模型标准化投影枚举映射不合法")


def _project_standardized_fields(
    payload: dict[str, Any], input_schema: dict[str, Any], projection: dict[str, Any]
) -> dict[str, Any]:
    """按当前模型版本的声明把输入字段投影为任务和计价使用的标准字段。"""

    validate_standardized_projection(input_schema, projection)
    projected = {field: None for field in _STANDARDIZED_FIELD_TYPES}
    for target, rule in projection.items():
        value = payload.get(rule["source"])
        if value is not None:
            projected[target] = rule.get("values", {}).get(str(value), value)
    return projected


def _validate_input_contract(payload: dict[str, Any], schema: dict[str, Any]) -> None:
    """按公开模型版本的受限 JSON 字段契约验证平铺动态字段。"""

    if not isinstance(schema, dict) or schema.get("type") != "object":
        raise ValueError("公开模型字段契约不合法")
    properties = schema.get("properties")
    required = schema.get("required", [])
    if not isinstance(properties, dict) or not isinstance(required, list):
        raise ValueError("公开模型字段契约不合法")
    input_fields = {key: value for key, value in payload.items() if key != "model"}
    unknown = set(input_fields) - set(properties)
    if unknown:
        raise ValidationError(
            f"请求包含模型不支持的字段：{sorted(unknown)[0]}",
            code="contract.unsupported_fields",
            params={"name": sorted(unknown)[0]},
        )
    provided_fields = set(input_fields) | {"model"}
    for field in required:
        if not isinstance(field, str) or field not in provided_fields:
            raise ValidationError(
                f"缺少模型必填字段：{field}",
                code="contract.missing_required_fields",
                params={"name": field},
            )
    for field, value in input_fields.items():
        _validate_field(field, value, properties[field])


def _validate_field(field: str, value: Any, rule: Any) -> None:
    """验证单个字段的基础类型、枚举和长度边界，拒绝不受支持的契约表达式。

    字段规则省略 ``type`` 时表示任意 JSON 类型，不做类型相关校验。
    """

    if not isinstance(rule, dict):
        raise ValidationError(
            f"模型字段契约不合法：{field}", code="contract.invalid_field_contract", params={"name": field}
        )
    field_type = rule.get("type")
    if field_type is None:
        return
    if not isinstance(field_type, str):
        raise ValidationError(
            f"模型字段契约不合法：{field}", code="contract.invalid_field_contract", params={"name": field}
        )
    matches = {
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, int | float) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "array": isinstance(value, list),
        "object": isinstance(value, dict),
    }
    if field_type not in matches or not matches[field_type]:
        raise ValidationError(
            f"字段 {field} 类型必须为 {field_type}",
            code="contract.field_type_mismatch",
            params={"name": field, "expected": field_type},
        )
    if "enum" in rule and value not in rule["enum"]:
        raise ValidationError(f"字段 {field} 不在允许枚举中", code="contract.field_not_in_enum", params={"name": field})
    if field_type == "string":
        if "minLength" in rule and len(value) < rule["minLength"]:
            raise ValidationError(
                f"字段 {field} 长度不足", code="contract.field_length_too_short", params={"name": field}
            )
        if "maxLength" in rule and len(value) > rule["maxLength"]:
            raise ValidationError(
                f"字段 {field} 长度超出限制", code="contract.field_length_too_long", params={"name": field}
            )
    if field_type == "array":
        if "minItems" in rule and len(value) < rule["minItems"]:
            raise ValidationError(f"字段 {field} 项数不足", code="contract.field_items_too_few", params={"name": field})
        if "maxItems" in rule and len(value) > rule["maxItems"]:
            raise ValidationError(
                f"字段 {field} 项数超出限制", code="contract.field_items_too_many", params={"name": field}
            )
    if field_type in {"integer", "number"}:
        if "minimum" in rule and value < rule["minimum"]:
            raise ValidationError(
                f"字段 {field} 小于最小值", code="contract.field_below_minimum", params={"name": field}
            )
        if "maximum" in rule and value > rule["maximum"]:
            raise ValidationError(
                f"字段 {field} 大于最大值", code="contract.field_above_maximum", params={"name": field}
            )
