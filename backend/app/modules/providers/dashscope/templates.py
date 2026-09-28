"""DashScope 原生 Provider 模板，声明千问与万相模型契约。

纯文本与多模态模型共用同一模板，具体端点由公开请求路径决定，无需为多模态模型单独选择模板；
视频模型能力与请求结构不同，由万相模板单独声明。
"""

from typing import Any

from app.modules.providers.openai_compatible.templates import _text_pricing_rules
from app.modules.providers.templates import ProviderTemplate

# 文本占位价：千问官方价未录入目录，目录未命中时按「同档高收」取三家厂商中的最高档。
_TEXT_INPUT_UNIT_AMOUNT = "15.000000"
_TEXT_CACHE_WRITE_UNIT_AMOUNT = "18.750000"
_TEXT_CACHED_INPUT_UNIT_AMOUNT = "7.500000"
_TEXT_OUTPUT_UNIT_AMOUNT = "60.000000"

DASHSCOPE_DEFAULT_TEMPLATE = ProviderTemplate(
    template_id="dashscope_default",
    provider_type="dashscope",
    label="千问",
    model_type="text",
    summary="DashScope 原生 Generation 接口，支持纯文本与多模态输入及增量流式输出。",
    tags=["千问", "DashScope", "文本对话", "多模态"],
    provider_id="qwen",
    provider_name="通义千问",
    input_schema={
        "type": "object",
        "required": ["input"],
        "properties": {
            "input": {"type": "object"},
            "parameters": {"type": "object"},
        },
    },
    example={
        "input": {"messages": [{"role": "user", "content": "你好，介绍一下你自己"}]},
        "parameters": {"result_format": "message"},
    },
    default_pricing_rules=_text_pricing_rules(
        input_price=_TEXT_INPUT_UNIT_AMOUNT,
        cache_write_price=_TEXT_CACHE_WRITE_UNIT_AMOUNT,
        cached_input_price=_TEXT_CACHED_INPUT_UNIT_AMOUNT,
        output_price=_TEXT_OUTPUT_UNIT_AMOUNT,
    ),
)


VIDEO_RESOLUTION_TIERS = ("480P", "720P", "1080P")
VIDEO_ASPECT_RATIOS = ("adaptive", "16:9", "4:3", "1:1", "3:4", "9:16")

VIDEO_OUTPUT_AMOUNTS = ("0.300000", "0.600000", "1.200000")
"""万相 3.0 按输出视频秒数计费的官方原价，依次对应 480P、720P、1080P。
"""


def _video_pricing_items(unit_amount: str) -> list[dict[str, Any]]:
    """生成单档分辨率的默认计费项，单价为每输出秒数的官方原价。"""

    return [
        {
            "label": "输出视频时长",
            "position": 0,
            "kind": "output_video_duration",
            "source_fields": ["seconds"],
            "free_quantity": 0,
            "unit_amount": unit_amount,
        }
    ]


def _video_pricing_rules() -> list[dict[str, Any]]:
    """按分辨率档位生成默认定价规则，条件命中请求的 ``resolution``。"""

    rules = [
        {
            "name": tier,
            "priority": priority,
            "conditions": [{"field": "resolution", "operator": "eq", "value": tier}],
            "items": _video_pricing_items(amount),
        }
        for priority, (tier, amount) in enumerate(
            zip(VIDEO_RESOLUTION_TIERS, VIDEO_OUTPUT_AMOUNTS, strict=True), start=10
        )
    ]
    rules.append(
        {
            # 兜底档位：请求未携带 resolution（如管理员把该字段改为可选）时按 480P 档计费，避免无方案命中。
            "name": "默认档位",
            "priority": 100,
            "conditions": [],
            "items": _video_pricing_items(VIDEO_OUTPUT_AMOUNTS[0]),
        }
    )
    return rules


DASHSCOPE_VIDEO_DEFAULT_TEMPLATE = ProviderTemplate(
    template_id="dashscope_video_default",
    provider_type="dashscope",
    label="万相 3.0 视频生成",
    model_type="video",
    summary="通过百炼 DashScope 原生异步接口生成万相 3.0 视频，支持文生视频、图生视频与参考生视频。",
    tags=["文生视频", "图生视频", "参考生视频", "万相"],
    provider_id="wan",
    provider_name="通义万相",
    input_schema={
        "type": "object",
        "required": ["seconds", "resolution"],
        "properties": {
            "prompt": {"type": "string", "minLength": 1, "maxLength": 20000},
            "seconds": {"type": "integer", "minimum": 2, "maximum": 30},
            "resolution": {"type": "string", "enum": list(VIDEO_RESOLUTION_TIERS)},
            "aspect_ratio": {"type": "string", "enum": list(VIDEO_ASPECT_RATIOS)},
            "seed": {"type": "integer", "minimum": -1, "maximum": 2147483647},
            "generate_audio": {"type": "boolean"},
            "prompt_extend": {"type": "boolean"},
            "watermark": {"type": "boolean"},
            "first_image": {"type": "string"},
            "last_image": {"type": "string"},
            "reference_images": {"type": "array", "items": {"type": "string"}, "maxItems": 10},
            "reference_videos": {"type": "array", "items": {"type": "string"}, "maxItems": 5},
            "reference_audios": {"type": "array", "items": {"type": "string"}, "maxItems": 5},
            "reference_file": {"type": "string"},
            "web_link": {"type": "string"},
        },
    },
    example={
        "prompt": "镜头缓慢推进，一只橘猫在窗边晒太阳",
        "seconds": 5,
        "resolution": "720P",
        "aspect_ratio": "16:9",
        "seed": 12345,
        "generate_audio": True,
    },
    material_fields={
        "first_image": {"categories": ["image"], "multiple": False},
        "last_image": {"categories": ["image"], "multiple": False},
        "reference_images": {"categories": ["image"], "multiple": True},
        "reference_videos": {"categories": ["video"], "multiple": True},
        "reference_audios": {"categories": ["audio"], "multiple": True},
    },
    default_pricing_rules=_video_pricing_rules(),
)
