from app.modules.providers.templates import ProviderTemplate

_STANDARD_OUTPUT_AMOUNTS = ("0.080000", "0.120000", "0.240000")
"""文生视频、图生视频只按输出视频时长计费，单价单位为 USD/秒，依次对应 480P、768P、1080P。"""

_REFERENCE_OUTPUT_AMOUNTS = ("0.260000", "0.380000", "0.760000")
"""参考生视频在输出视频时长之外还按参考素材 Token 计费，输出时长单价独立于文生、图生。"""


def _template(
    template_id: str,
    endpoint: str,
    label: str,
    summary: str,
    properties: dict,
    required: list[str],
    example: dict,
    material_fields: dict | None = None,
    material_pricing: bool = False,
    output_amounts: tuple[str, str, str] = _STANDARD_OUTPUT_AMOUNTS,
) -> ProviderTemplate:
    low_amount, middle_amount, high_amount = output_amounts
    rules = [
        {
            "name": "480P",
            "priority": 10,
            "conditions": [{"field": "resolution", "operator": "eq", "value": "480P"}],
            "items": _pricing_items(low_amount, material_pricing),
        },
        {
            "name": "768P",
            "priority": 20,
            "conditions": [{"field": "resolution", "operator": "eq", "value": "768P"}],
            "items": _pricing_items(middle_amount, material_pricing),
        },
        {
            # 1080P 输出时长单价为 768P 的两倍，素材单价同样翻倍。
            "name": "1080P",
            "priority": 30,
            "conditions": [{"field": "resolution", "operator": "eq", "value": "1080P"}],
            "items": _pricing_items(high_amount, material_pricing, material_amount="0.326400"),
        },
        {
            # 兜底档位：请求未携带 resolution（如管理员把该字段改为可选）时按 480P 档计费，避免无方案命中。
            "name": "默认档位",
            "priority": 40,
            "conditions": [],
            "items": _pricing_items(low_amount, material_pricing),
        },
    ]
    return ProviderTemplate(
        template_id=template_id,
        provider_type="fal",
        label=label,
        model_type="video",
        summary=summary,
        tags=["视频生成", "fal 同步"],
        provider_id="fal",
        provider_name="fal",
        input_schema={"type": "object", "required": required, "properties": properties},
        example=example,
        material_fields=material_fields or {},
        default_pricing_rules=rules,
        provider_config={
            "endpoint": endpoint,
            "allowed_fields": list(properties),
            "field_mapping": {"seconds": "duration"},
        },
    )


def _pricing_items(
    output_amount: str, material_pricing: bool, material_amount: str = "0.163200"
) -> list[dict[str, object]]:
    items: list[dict[str, object]] = [
        {
            "label": "输出视频时长",
            "position": 0,
            "kind": "output_video_duration",
            "source_fields": ["seconds"],
            "free_quantity": 0,
            "unit_amount": output_amount,
        }
    ]
    if material_pricing:
        items.append(
            {
                "label": "参考素材 Token",
                "position": 1,
                "kind": "input_material_tokens",
                "source_fields": [
                    "reference_image_urls",
                    "reference_video_urls",
                    "reference_audio_urls",
                ],
                "free_quantity": 4096,
                "unit_amount": material_amount,
            }
        )
    return items


_COMMON_PROPERTIES = {
    "prompt": {"type": "string", "minLength": 1},
    "prompt_expansion_mode": {"type": "string", "enum": ["balanced", "quality"]},
    "seconds": {"type": "integer", "minimum": 5, "maximum": 15},
    "resolution": {"type": "string", "enum": ["480P", "768P", "1080P"]},
    "aspect_ratio": {"type": "string", "enum": ["21:9", "16:9", "4:3", "1:1", "3:4", "9:16"]},
    "seed": {"type": "integer"},
}

FAL_MINIMAX_H3_MAX_TEXT_TO_VIDEO_TEMPLATE = _template(
    template_id="fal_minimax_h3_max_text_to_video",
    endpoint="minimax/h3-max/text-to-video",
    label="fal MiniMax H3 Max 文生视频",
    summary="通过 fal 同步接口根据文本提示词生成视频。",
    properties=_COMMON_PROPERTIES,
    required=["prompt", "prompt_expansion_mode", "resolution"],
    example={
        "prompt": "镜头缓慢推进，一只橘猫在窗边晒太阳",
        "prompt_expansion_mode": "balanced",
        "seconds": 5,
        "resolution": "768P",
        "aspect_ratio": "16:9",
    },
)

FAL_MINIMAX_H3_MAX_REFERENCE_TO_VIDEO_TEMPLATE = _template(
    "fal_minimax_h3_max_reference_to_video",
    "minimax/h3-max/reference-to-video",
    "fal MiniMax H3 Max 参考生视频",
    "通过 fal 同步接口根据参考图片、视频或音频生成视频。",
    {
        **_COMMON_PROPERTIES,
        "reference_image_urls": {"type": "array", "items": {"type": "string"}, "maxItems": 9},
        "reference_video_urls": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
        "reference_audio_urls": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
    },
    ["prompt", "prompt_expansion_mode", "resolution"],
    {
        "prompt": "参考素材中的人物向镜头挥手",
        "prompt_expansion_mode": "balanced",
        "seconds": 5,
    },
    {
        "reference_image_urls": {"categories": ["image"], "multiple": True, "measure_dimensions": True},
        "reference_video_urls": {"categories": ["video"], "multiple": True},
        "reference_audio_urls": {"categories": ["audio"], "multiple": True},
    },
    material_pricing=True,
    output_amounts=_REFERENCE_OUTPUT_AMOUNTS,
)

FAL_MINIMAX_H3_MAX_IMAGE_TO_VIDEO_TEMPLATE = _template(
    "fal_minimax_h3_max_image_to_video",
    "minimax/h3-max/image-to-video",
    "fal MiniMax H3 Max 图生视频",
    "通过 fal 同步接口根据首帧和尾帧图片生成视频。",
    {
        **_COMMON_PROPERTIES,
        "image_url": {"type": "string", "minLength": 1},
        "end_image_url": {"type": "string", "minLength": 1},
    },
    ["prompt", "prompt_expansion_mode", "resolution"],
    {
        "prompt": "镜头慢慢拉远",
        "prompt_expansion_mode": "balanced",
        "seconds": 5,
    },
    {
        "image_url": {"categories": ["image"], "multiple": False},
        "end_image_url": {"categories": ["image"], "multiple": False},
    },
)
