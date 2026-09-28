from typing import Any

from app.modules.providers.templates import ProviderTemplate

_VIDEO_SIZE_TIERS: tuple[tuple[str, int, str | None, list[str]], ...] = (
    (
        "480P",
        10,
        "0.030000",
        ["864x480", "480x864", "640x640", "544x800", "800x544", "576x736", "736x576", "992x416"],
    ),
    (
        "768P",
        20,
        "0.070000",
        ["1376x768", "768x1376", "1024x1024", "832x1248", "1248x832", "896x1184", "1184x896", "1568x672"],
    ),
    (
        "1080P",
        30,
        "0.120000",
        ["1920x1088", "1088x1920", "1440x1440", "1184x1760", "1760x1184", "1248x1664", "1664x1248", "2208x960"],
    ),
    ("2K", 40, "0.150000", ["2K"]),
    ("4K", 50, "0.170000", ["4K"]),
)


def _tier_pricing_items(output_unit_amount: str | None) -> list[dict[str, Any]]:
    """生成单档尺寸的默认计费项，仅输出时长基础单价随档位变化。"""

    return [
        {
            "label": "输出视频时长",
            "position": 0,
            "kind": "output_video_duration",
            "source_fields": ["seconds"],
            "free_quantity": 0,
            "unit_amount": output_unit_amount,
        },
        {
            "label": "输入视频时长",
            "position": 1,
            "kind": "input_video_duration",
            "source_fields": ["reference_video", "reference_videos", "input_reference"],
            "free_quantity": 0,
            "unit_amount": None,
        },
        {
            "label": "输入图片",
            "position": 2,
            "kind": "input_image_fixed",
            "source_fields": ["images", "input_reference"],
            "free_quantity": 5,
            "unit_amount": "0.100000",
        },
    ]


def _default_pricing_rules() -> list[dict[str, Any]]:
    """按 480P/768P/1080P/2K/4K 档位生成默认定价规则，条件命中请求的 ``size``。"""

    return [
        {
            "name": tier,
            "priority": priority,
            "conditions": [{"field": "size", "operator": "in", "value": sizes}],
            "items": _tier_pricing_items(unit_amount),
        }
        for tier, priority, unit_amount, sizes in _VIDEO_SIZE_TIERS
    ]


MINIMAX_H3_DEFAULT_TEMPLATE = ProviderTemplate(
    template_id="minimax_h3_default",
    provider_type="minimax_h3",
    label="Hook MiniMax H3",
    model_type="video",
    summary="根据文本或参考素材生成短视频。",
    tags=["文生视频", "图生视频"],
    provider_id="minimax",
    provider_name="MiniMax",
    input_schema={
        "type": "object",
        "required": ["prompt", "seconds", "size"],
        "properties": {
            "prompt": {"type": "string"},
            "seconds": {"type": "integer", "minimum": 4, "maximum": 15},
            "size": {
                "type": "string",
                "enum": [
                    "864x480",
                    "1376x768",
                    "1920x1088",
                    "480x864",
                    "768x1376",
                    "1088x1920",
                    "640x640",
                    "1024x1024",
                    "1440x1440",
                    "544x800",
                    "832x1248",
                    "1184x1760",
                    "800x544",
                    "1248x832",
                    "1760x1184",
                    "576x736",
                    "896x1184",
                    "1248x1664",
                    "736x576",
                    "1184x896",
                    "1664x1248",
                    "992x416",
                    "1568x672",
                    "2208x960",
                    "2K",
                    "4K",
                ],
            },
            "aspect_ratio": {
                "type": "string",
                "enum": ["1:1", "2:3", "3:2", "3:4", "4:3", "9:16", "16:9", "21:9"],
            },
            "mode": {"type": "string"},
            "prompt_enhance": {"type": "boolean"},
            "input_reference": {"type": "string"},
            "images": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 9},
            "reference_video": {"type": "string"},
            "reference_audio": {"type": "string"},
            "reference_videos": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 3},
            "reference_audios": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 3},
        },
    },
    example={
        "prompt": "镜头缓慢推进，一只橘猫在窗边晒太阳",
        "seconds": 5,
        "size": "1376x768",
    },
    material_fields={
        "images": {"categories": ["image"], "multiple": True},
        "input_reference": {"categories": ["image", "video"], "multiple": False},
        "reference_video": {"categories": ["video"], "multiple": False},
        "reference_videos": {"categories": ["video"], "multiple": True},
        "reference_audio": {"categories": ["audio"], "multiple": False},
        "reference_audios": {"categories": ["audio"], "multiple": True},
    },
    default_pricing_rules=_default_pricing_rules(),
)
