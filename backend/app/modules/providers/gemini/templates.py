"""Gemini 原生文本与图像 Provider 模板。"""

from app.modules.providers.openai_compatible.templates import _image_token_pricing_rules, _text_pricing_rules
from app.modules.providers.templates import ProviderTemplate

# 文本占位价：目录未命中时的兜底价，取 Gemini 现行目录最高档
# （3.1 Pro / 3 Pro：输入 2、缓存写入 2.5、缓存命中 0.2、输出 12）。
_TEXT_INPUT_UNIT_AMOUNT = "2.000000"
_TEXT_CACHE_WRITE_UNIT_AMOUNT = "2.500000"
_TEXT_CACHED_INPUT_UNIT_AMOUNT = "0.200000"
_TEXT_OUTPUT_UNIT_AMOUNT = "12.000000"

# 图片占位价：目录未命中时的兜底价，取 Gemini 图片现行目录最高档（gemini-3-pro-image）。
_IMAGE_TOKEN_INPUT_UNIT_AMOUNT = "2.000000"
_IMAGE_TOKEN_OUTPUT_UNIT_AMOUNT = "120.000000"
_IMAGE_INPUT_TOKENS_PER_IMAGE = "1032"
_IMAGE_OUTPUT_TOKENS_PER_IMAGE = "1117"
_IMAGE_TEXT_CHARS_PER_TOKEN = "2"
_IMAGE_UNKNOWN_TILES_PER_IMAGE = "4"


GEMINI_TEXT_DEFAULT_TEMPLATE = ProviderTemplate(
    template_id="gemini_text_default",
    provider_type="gemini",
    label="Gemini",
    model_type="text",
    summary="Gemini 原生 generateContent 与流式内容生成。",
    tags=["Gemini", "文本对话", "流式输出"],
    provider_id="google",
    provider_name="Google",
    input_schema={
        "type": "object",
        "required": ["contents"],
        "properties": {
            "contents": {"type": "array", "minItems": 1},
            "systemInstruction": {"type": "object"},
            "generationConfig": {"type": "object"},
            "safetySettings": {"type": "array"},
            "tools": {"type": "array"},
            "toolConfig": {"type": "object"},
        },
    },
    example={"contents": [{"role": "user", "parts": [{"text": "你好，介绍一下你自己"}]}]},
    default_pricing_rules=_text_pricing_rules(
        input_price=_TEXT_INPUT_UNIT_AMOUNT,
        cache_write_price=_TEXT_CACHE_WRITE_UNIT_AMOUNT,
        cached_input_price=_TEXT_CACHED_INPUT_UNIT_AMOUNT,
        output_price=_TEXT_OUTPUT_UNIT_AMOUNT,
    ),
)


GEMINI_IMAGE_DEFAULT_TEMPLATE = ProviderTemplate(
    template_id="gemini_image_default",
    provider_type="gemini",
    label="Gemini",
    model_type="image",
    summary="Gemini 原生图像生成与图像编辑，响应以 inlineData 返回图片。",
    tags=["Gemini", "Nano Banana", "文生图", "图片编辑"],
    provider_id="google",
    provider_name="Google",
    input_schema={
        "type": "object",
        "required": ["contents"],
        "properties": {
            "contents": {"type": "array", "minItems": 1},
            "systemInstruction": {"type": "object"},
            "generationConfig": {"type": "object"},
            "safetySettings": {"type": "array"},
            "tools": {"type": "array"},
            "toolConfig": {"type": "object"},
        },
    },
    example={
        "contents": [
            {"parts": [{"text": "一只戴墨镜的橘猫，电影感光影"}]},
        ]
    },
    default_pricing_rules=_image_token_pricing_rules(
        input_price=_IMAGE_TOKEN_INPUT_UNIT_AMOUNT,
        output_price=_IMAGE_TOKEN_OUTPUT_UNIT_AMOUNT,
        input_image_tokens_per_image=_IMAGE_INPUT_TOKENS_PER_IMAGE,
        output_image_tokens_per_image=_IMAGE_OUTPUT_TOKENS_PER_IMAGE,
        text_chars_per_token=_IMAGE_TEXT_CHARS_PER_TOKEN,
        unknown_image_tiles_per_image=_IMAGE_UNKNOWN_TILES_PER_IMAGE,
    ),
)
