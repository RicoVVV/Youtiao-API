"""OpenAI 兼容图片与文本 Provider 模板，声明公开模型契约与默认定价方案。"""

from typing import Any

from app.modules.providers.templates import ProviderTemplate

# 文本占位价：目录未命中时用的兜底价，一律取该厂商的高档，宁可多收不可少收。
# 本组取 OpenAI 现行目录的最高档（pro 档：输入 30、输出 180，即 gpt-5.5-pro / gpt-5.4-pro），
# 缓存写入按 1.25 倍输入价、缓存命中按最不利的 0.5 倍输入价推导。各厂商模板传入自己的数值。
_TEXT_INPUT_UNIT_AMOUNT = "30.000000"
_TEXT_CACHE_WRITE_UNIT_AMOUNT = "37.500000"
_TEXT_CACHED_INPUT_UNIT_AMOUNT = "15.000000"
_TEXT_OUTPUT_UNIT_AMOUNT = "180.000000"

# 图片占位价与每张图片的 Token 估算参数，取 OpenAI 图片目录最高档（gpt-image-1.5 的输出价）。
# 估算参数与 model_catalog 中的同名常量含义一致，仅在响应未上报用量时兜底。
_IMAGE_TOKEN_INPUT_UNIT_AMOUNT = "8.000000"
_IMAGE_TOKEN_OUTPUT_UNIT_AMOUNT = "32.000000"
_IMAGE_INPUT_TOKENS_PER_IMAGE = "630"
_IMAGE_OUTPUT_TOKENS_PER_IMAGE = "1117"
_IMAGE_TEXT_CHARS_PER_TOKEN = "2"
# 平台图片 Token 校验强制要求该参数，OpenAI 侧不会用到（只有 Gemini 按 tile 估算）。
_IMAGE_UNKNOWN_TILES_PER_IMAGE = "4"

# 图片按次计费的占位单价：1K/2K/4K 统一为 1 USD/次，管理员可在定价面板按档位调整。
_IMAGE_COUNT_UNIT_AMOUNT = "1.000000"

_VIDEO_OUTPUT_UNIT_AMOUNT = "0.100000"


def _image_token_pricing_rules(
    *,
    input_price: str,
    output_price: str,
    input_image_tokens_per_image: str,
    output_image_tokens_per_image: str,
    text_chars_per_token: str,
    unknown_image_tiles_per_image: str,
) -> list[dict[str, Any]]:
    """生成图片按 Token 计费的默认规则。

    平台图片 Token 计费要求输入与输出两项同时存在且各自声明估算参数，因此这里生成一条完整
    规则。数量优先取上游上报的真实用量，估算参数只在未上报时兜底。
    """

    return [
        {
            "name": "按图片 token 计费",
            "priority": 10,
            "conditions": [],
            "items": [
                {
                    "label": "输入图片 token",
                    "position": 0,
                    "kind": "input_image_tokens",
                    "source_fields": [],
                    "free_quantity": 0,
                    "unit_amount": input_price,
                    "estimate_config": {
                        "input_image_tokens_per_image": input_image_tokens_per_image,
                        "text_chars_per_token": text_chars_per_token,
                        "gemini_unknown_image_tiles_per_image": unknown_image_tiles_per_image,
                    },
                },
                {
                    "label": "输出图片 token",
                    "position": 1,
                    "kind": "output_image_tokens",
                    "source_fields": [],
                    "free_quantity": 0,
                    "unit_amount": output_price,
                    "estimate_config": {
                        "output_image_tokens_per_image": output_image_tokens_per_image,
                    },
                },
            ],
        }
    ]


def _image_request_pricing_rules(*, unit_amount: str) -> list[dict[str, Any]]:
    """生成图片按次计费的默认规则，按输出像素分档并保留无条件兜底档。

    每次请求固定计费一次，不依赖请求张数字段；像素档位由模板从 ``size`` 派生，
    请求未携带尺寸时由兜底档承接，避免选不出计费方案。
    """

    tiers = (
        ("4K 图片", {"field": "image_pixel_count", "operator": "gte", "value": 8000000}),
        ("2K 图片", {"field": "image_pixel_count", "operator": "between", "value": [2000000, 7999999]}),
        ("1K 图片", {"field": "image_pixel_count", "operator": "between", "value": [1, 1999999]}),
    )
    item = {
        "label": "图片请求",
        "position": 0,
        "kind": "request_fixed",
        "source_fields": [],
        "free_quantity": 0,
        "unit_amount": unit_amount,
    }
    rules = [{"name": name, "conditions": [condition], "items": [dict(item)]} for name, condition in tiers]
    rules.append({"name": "未传尺寸图片", "conditions": [], "items": [dict(item)]})
    return rules


def _text_pricing_rules(
    *,
    input_price: str,
    cache_write_price: str,
    cached_input_price: str,
    output_price: str,
) -> list[dict[str, Any]]:
    """生成文本 token 后付费计费规则，数量来自上游返回的用量。

    固定四项：普通输入、缓存写入输入、缓存命中输入与输出。没有官方缓存写入价的模型把写入项
    单价传 0，计费项存在但不产生金额。
    """

    return [
        {
            "name": "按 token 计费",
            "priority": 10,
            "conditions": [],
            "items": [
                {
                    "label": "输入 token",
                    "position": 0,
                    "kind": "input_text_tokens",
                    "source_fields": [],
                    "free_quantity": 0,
                    "unit_amount": input_price,
                },
                {
                    "label": "缓存写入 token",
                    "position": 1,
                    "kind": "cache_write_input_text_tokens",
                    "source_fields": [],
                    "free_quantity": 0,
                    "unit_amount": cache_write_price,
                },
                {
                    "label": "缓存命中输入 token",
                    "position": 2,
                    "kind": "cached_input_text_tokens",
                    "source_fields": [],
                    "free_quantity": 0,
                    "unit_amount": cached_input_price,
                },
                {
                    "label": "输出 token",
                    "position": 3,
                    "kind": "output_text_tokens",
                    "source_fields": [],
                    "free_quantity": 0,
                    "unit_amount": output_price,
                },
            ],
        }
    ]


def _video_pricing_rules() -> list[dict[str, Any]]:
    return [
        {
            "name": "按视频时长计费",
            "priority": 10,
            "conditions": [],
            "items": [
                {
                    "label": "输出视频时长",
                    "position": 0,
                    "kind": "output_video_duration",
                    "source_fields": ["seconds"],
                    "free_quantity": 0,
                    "unit_amount": _VIDEO_OUTPUT_UNIT_AMOUNT,
                }
            ],
        }
    ]


OPENAI_IMAGE_DEFAULT_TEMPLATE = ProviderTemplate(
    template_id="openai_image_default",
    provider_type="openai_compatible",
    label="OpenAI",
    model_type="image",
    summary="根据文本提示词生成图片，并支持带输入图片的编辑。",
    tags=["文生图", "图片编辑"],
    provider_id="openai",
    provider_name="OpenAI",
    input_schema={
        "type": "object",
        "required": ["prompt"],
        "properties": {
            "prompt": {"type": "string", "minLength": 1},
            "size": {"type": "string"},
            "quality": {"type": "string", "enum": ["auto", "low", "medium", "high"]},
            "response_format": {"type": "string", "enum": ["url", "b64_json"]},
            "background": {"type": "string", "enum": ["auto", "transparent", "opaque"]},
            "output_format": {"type": "string", "enum": ["png", "jpeg", "webp"]},
        },
    },
    example={
        "prompt": "一只戴墨镜的橘猫，电影感光影",
        "size": "1024x1024",
    },
    derived_pricing_fields=[{"type": "image_pixel_count", "size_source": "size"}],
    default_pricing_rules=_image_token_pricing_rules(
        input_price=_IMAGE_TOKEN_INPUT_UNIT_AMOUNT,
        output_price=_IMAGE_TOKEN_OUTPUT_UNIT_AMOUNT,
        input_image_tokens_per_image=_IMAGE_INPUT_TOKENS_PER_IMAGE,
        output_image_tokens_per_image=_IMAGE_OUTPUT_TOKENS_PER_IMAGE,
        text_chars_per_token=_IMAGE_TEXT_CHARS_PER_TOKEN,
        unknown_image_tiles_per_image=_IMAGE_UNKNOWN_TILES_PER_IMAGE,
    ),
)


# 同一 OpenAI 图片端点的按次计费模板：请求契约与 token 模板一致，只把默认计费方案换成
# 按输出像素分档的固定次数计费；创建模型时选择该模板即自动播种，无需手填定价规则。
OPENAI_IMAGE_PER_REQUEST_DEFAULT_TEMPLATE = ProviderTemplate(
    template_id="openai_image_per_request_default",
    provider_type="openai_compatible",
    label="OpenAI（按次）",
    model_type="image",
    summary="根据文本提示词生成图片并按请求次数计费，支持 1K/2K/4K 像素档位。",
    tags=["文生图", "图片编辑", "按次计费"],
    provider_id="openai",
    provider_name="OpenAI",
    input_schema={
        "type": "object",
        "required": ["prompt"],
        "properties": {
            "prompt": {"type": "string", "minLength": 1},
            "size": {"type": "string"},
            "quality": {"type": "string", "enum": ["auto", "low", "medium", "high"]},
            "response_format": {"type": "string", "enum": ["url", "b64_json"]},
            "background": {"type": "string", "enum": ["auto", "transparent", "opaque"]},
            "output_format": {"type": "string", "enum": ["png", "jpeg", "webp"]},
        },
    },
    example={
        "prompt": "一只戴墨镜的橘猫，电影感光影",
        "size": "1024x1024",
    },
    derived_pricing_fields=[{"type": "image_pixel_count", "size_source": "size"}],
    default_pricing_rules=_image_request_pricing_rules(unit_amount=_IMAGE_COUNT_UNIT_AMOUNT),
)


# 单一 OpenAI 文本模板，同时承载 Chat Completions 与 Responses 两种请求形状：
# 公开路径决定实际打到哪个上游端点（/v1/chat/completions 或 /v1/responses），因此模板不强制
# 某一个请求字段，改由适配器按端点分别校验 messages 与 input。
OPENAI_TEXT_DEFAULT_TEMPLATE = ProviderTemplate(
    template_id="openai_text_default",
    provider_type="openai_compatible",
    label="OpenAI",
    model_type="text",
    summary="OpenAI 兼容的文本生成，可分别按 Chat Completions 与 Responses 请求形状调用，支持普通与流式响应。",
    tags=["文本对话", "Responses API", "流式输出"],
    provider_id="openai",
    provider_name="OpenAI",
    input_schema={
        "type": "object",
        "required": [],
        "properties": {
            "messages": {"type": "array", "minItems": 1},
            "input": {},
            "instructions": {"type": "string"},
            "temperature": {"type": "number", "minimum": 0, "maximum": 2},
            "top_p": {"type": "number", "minimum": 0, "maximum": 1},
            "max_tokens": {"type": "integer", "minimum": 1},
            "max_output_tokens": {"type": "integer", "minimum": 1},
            "stream": {"type": "boolean"},
            "stream_options": {"type": "object"},
            "stop": {"type": "array"},
            "presence_penalty": {"type": "number"},
            "frequency_penalty": {"type": "number"},
            "tools": {"type": "array"},
            "tool_choice": {},
            "parallel_tool_calls": {"type": "boolean"},
            "reasoning": {"type": "object"},
        },
    },
    example={
        "messages": [{"role": "user", "content": "你好，介绍一下你自己"}],
    },
    default_pricing_rules=_text_pricing_rules(
        input_price=_TEXT_INPUT_UNIT_AMOUNT,
        cache_write_price=_TEXT_CACHE_WRITE_UNIT_AMOUNT,
        cached_input_price=_TEXT_CACHED_INPUT_UNIT_AMOUNT,
        output_price=_TEXT_OUTPUT_UNIT_AMOUNT,
    ),
)


OPENAI_VIDEO_DEFAULT_TEMPLATE = ProviderTemplate(
    template_id="openai_video_default",
    provider_type="openai_compatible",
    label="OpenAI Video",
    model_type="video",
    summary="通过 OpenAI 兼容视频接口创建、查询和下载视频任务。",
    tags=["文生视频", "视频任务"],
    provider_id="openai",
    provider_name="OpenAI",
    input_schema={
        "type": "object",
        "required": ["prompt", "seconds", "size"],
        "properties": {
            "prompt": {"type": "string", "minLength": 1},
            "seconds": {"type": "integer", "minimum": 1},
            "size": {"type": "string", "enum": ["720x1280", "1280x720", "1024x1792", "1792x1024"]},
            "input_reference": {"type": "string"},
        },
    },
    example={
        "prompt": "镜头缓慢推进，一只橘猫在窗边晒太阳",
        "seconds": 8,
        "size": "1280x720",
    },
    material_fields={"input_reference": {"categories": ["image", "video"], "multiple": False}},
    default_pricing_rules=_video_pricing_rules(),
)
