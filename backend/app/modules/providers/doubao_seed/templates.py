"""豆包 Seed Provider 模板，声明火山方舟 Responses 模型契约。"""

from app.modules.providers.openai_compatible.templates import _text_pricing_rules
from app.modules.providers.templates import ProviderTemplate

# 文本占位价：豆包官方价未录入目录，目录未命中时按「同档高收」取三家厂商中的最高档。
_TEXT_INPUT_UNIT_AMOUNT = "15.000000"
_TEXT_CACHE_WRITE_UNIT_AMOUNT = "18.750000"
_TEXT_CACHED_INPUT_UNIT_AMOUNT = "7.500000"
_TEXT_OUTPUT_UNIT_AMOUNT = "60.000000"

DOUBAO_SEED_DEFAULT_TEMPLATE = ProviderTemplate(
    template_id="doubao_seed_default",
    provider_type="doubao_seed",
    label="豆包",
    model_type="text",
    summary="火山方舟原生 Responses 接口，支持同步与流式事件。",
    tags=["豆包", "Seed", "方舟", "Responses"],
    provider_id="volcengine",
    provider_name="火山引擎",
    input_schema={
        "type": "object",
        "required": ["input"],
        "properties": {
            "input": {},
            "instructions": {"type": "string"},
            "stream": {"type": "boolean"},
            "max_output_tokens": {"type": "integer", "minimum": 1},
            "temperature": {"type": "number", "minimum": 0, "maximum": 2},
            "top_p": {"type": "number", "minimum": 0, "maximum": 1},
            "thinking": {"type": "object"},
            "tools": {"type": "array"},
            "tool_choice": {},
            "previous_response_id": {"type": "string"},
        },
    },
    example={"input": "用一句话介绍你自己"},
    default_pricing_rules=_text_pricing_rules(
        input_price=_TEXT_INPUT_UNIT_AMOUNT,
        cache_write_price=_TEXT_CACHE_WRITE_UNIT_AMOUNT,
        cached_input_price=_TEXT_CACHED_INPUT_UNIT_AMOUNT,
        output_price=_TEXT_OUTPUT_UNIT_AMOUNT,
    ),
)
