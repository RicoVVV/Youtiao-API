"""Anthropic Messages Provider 模板，声明原生 Messages 请求契约。"""

from app.modules.providers.openai_compatible.templates import _text_pricing_rules
from app.modules.providers.templates import ProviderTemplate

# 文本占位价：目录未命中时的兜底价，取 Anthropic 现行目录最高档
# （Opus 4 / 4.1：输入 15、缓存写入 18.75、缓存命中 1.5、输出 75）。
_TEXT_INPUT_UNIT_AMOUNT = "15.000000"
_TEXT_CACHE_WRITE_UNIT_AMOUNT = "18.750000"
_TEXT_CACHED_INPUT_UNIT_AMOUNT = "1.500000"
_TEXT_OUTPUT_UNIT_AMOUNT = "75.000000"

ANTHROPIC_MESSAGES_DEFAULT_TEMPLATE = ProviderTemplate(
    template_id="anthropic_messages_default",
    provider_type="anthropic",
    label="Anthropic Messages",
    model_type="text",
    summary="Anthropic 原生 Messages 接口，支持同步与流式响应。",
    tags=["Claude", "Anthropic", "文本对话"],
    provider_id="anthropic",
    provider_name="Anthropic",
    input_schema={
        "type": "object",
        "required": ["messages", "max_tokens"],
        "properties": {
            "messages": {"type": "array", "minItems": 1},
            "max_tokens": {"type": "integer", "minimum": 1},
            "system": {},
            "temperature": {"type": "number", "minimum": 0, "maximum": 1},
            "top_p": {"type": "number", "minimum": 0, "maximum": 1},
            "top_k": {"type": "integer", "minimum": 1},
            "stop_sequences": {"type": "array"},
            "stream": {"type": "boolean"},
            "tools": {"type": "array"},
            "tool_choice": {"type": "object"},
            "thinking": {"type": "object"},
        },
    },
    example={
        "messages": [{"role": "user", "content": "你好，介绍一下你自己"}],
        "max_tokens": 1024,
    },
    default_pricing_rules=_text_pricing_rules(
        input_price=_TEXT_INPUT_UNIT_AMOUNT,
        cache_write_price=_TEXT_CACHE_WRITE_UNIT_AMOUNT,
        cached_input_price=_TEXT_CACHED_INPUT_UNIT_AMOUNT,
        output_price=_TEXT_OUTPUT_UNIT_AMOUNT,
    ),
)
