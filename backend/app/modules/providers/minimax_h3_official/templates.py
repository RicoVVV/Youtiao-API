from app.modules.providers.templates import ProviderTemplate

_RESOLUTION_SIZES = [
    "1376x768",
    "768x1376",
    "1024x1024",
    "832x1248",
    "1248x832",
    "896x1184",
    "1184x896",
    "1568x672",
    "2K",
]


MINIMAX_H3_OFFICIAL_DEFAULT_TEMPLATE = ProviderTemplate(
    template_id="minimax_h3_official_default",
    provider_type="minimax_h3_official",
    label="MiniMax H3 Official",
    model_type="video",
    summary="通过 MiniMax 官方 Video Generation V2 异步接口生成视频。",
    tags=["文生视频", "参考生视频", "MiniMax 官方"],
    provider_id="minimax",
    provider_name="MiniMax",
    input_schema={
        "type": "object",
        "required": ["prompt", "seconds", "size"],
        "properties": {
            "model": {"type": "string"},
            "prompt": {"type": "string", "minLength": 1},
            "seconds": {"type": "integer", "minimum": 1, "maximum": 15},
            "size": {"type": "string", "enum": _RESOLUTION_SIZES},
            "aspect_ratio": {
                "type": "string",
                "enum": ["1:1", "2:3", "3:2", "3:4", "4:3", "9:16", "16:9", "21:9", "adaptive"],
            },
            "images": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 9},
            "input_reference": {"type": "string"},
            "reference_video": {"type": "string"},
            "reference_videos": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 3},
            "reference_audio": {"type": "string"},
            "reference_audios": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 3},
            "callback_url": {"type": "string"},
            "aigc_watermark": {"type": "boolean"},
        },
    },
    example={
        "prompt": "镜头缓慢推进，一只橘猫在窗边晒太阳",
        "seconds": 6,
        "size": "1376x768",
        "aspect_ratio": "16:9",
    },
    material_fields={
        "images": {"categories": ["image"], "multiple": True},
        "input_reference": {"categories": ["image"], "multiple": False},
        "reference_video": {"categories": ["video"], "multiple": False},
        "reference_videos": {"categories": ["video"], "multiple": True},
        "reference_audio": {"categories": ["audio"], "multiple": False},
        "reference_audios": {"categories": ["audio"], "multiple": True},
    },
    default_pricing_rules=[
        {
            "name": "768P",
            "priority": 10,
            "conditions": [{"field": "size", "operator": "in", "value": _RESOLUTION_SIZES[:-1]}],
            "items": [
                {
                    "label": "输出视频时长",
                    "position": 0,
                    "kind": "output_video_duration",
                    "source_fields": ["seconds"],
                    "free_quantity": 0,
                    "unit_amount": None,
                }
            ],
        },
        {
            "name": "2K",
            "priority": 20,
            "conditions": [{"field": "size", "operator": "eq", "value": "2K"}],
            "items": [
                {
                    "label": "输出视频时长",
                    "position": 0,
                    "kind": "output_video_duration",
                    "source_fields": ["seconds"],
                    "free_quantity": 0,
                    "unit_amount": None,
                }
            ],
        },
        {
            # 兜底档位：请求未携带 size（如管理员把该字段改为可选）时按常规档计费，避免无方案命中。
            "name": "默认档位",
            "priority": 30,
            "conditions": [],
            "items": [
                {
                    "label": "输出视频时长",
                    "position": 0,
                    "kind": "output_video_duration",
                    "source_fields": ["seconds"],
                    "free_quantity": 0,
                    "unit_amount": None,
                }
            ],
        },
    ],
)
