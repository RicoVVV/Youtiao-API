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
    summary="Anthropic Claude 文本生成，原生 Messages 与 OpenAI Chat / Responses 协议均可调用，支持同步与流式响应。",
    tags=["Claude", "Anthropic", "文本对话", "Responses API", "流式输出"],
    provider_id="anthropic",
    provider_name="Anthropic",
    # 单一模板同时承载 Anthropic Messages 原生请求与 OpenAI Chat / Responses 请求形状：
    # 公开路径决定调用形状（/v1/messages、/v1/chat/completions、/v1/responses），因此不强制某一个
    # 请求字段，改由适配器按端点分别校验 messages 与 input。
    input_schema={
        "type": "object",
        "required": [],
        "properties": {
            "messages": {"type": "array", "minItems": 1},
            "input": {},
            "instructions": {"type": "string"},
            "system": {},
            "max_tokens": {"type": "integer", "minimum": 1},
            "max_completion_tokens": {"type": "integer", "minimum": 1},
            "max_output_tokens": {"type": "integer", "minimum": 1},
            "temperature": {"type": "number"},
            "top_p": {"type": "number"},
            "top_k": {"type": "integer", "minimum": 1},
            "stop": {},
            "stop_sequences": {"type": "array"},
            "stream": {"type": "boolean"},
            "stream_options": {"type": "object"},
            "tools": {"type": "array"},
            "tool_choice": {},
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
