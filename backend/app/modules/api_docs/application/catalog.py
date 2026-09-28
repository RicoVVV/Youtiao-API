"""接口文档目录声明。

目录分三级声明：能力（文本、图片、视频）、模型族、可独立调用的条目。模型族与调用协议无关：
族是模型产品线的属性，而调用协议由能力决定（视频模型统一走 OpenAI 兼容端点），因此同一族的模型
可以绑不同模板、同一模板也可以服务不同族的模型，族必须在条目上声明而不能从模板推导。

条目只声明「引用哪些模板」，参数、示例与端点一律取自模板与公开协议声明，避免出现第二份来源。
"""

from dataclasses import dataclass, field

CAPABILITY_ORDER: tuple[str, ...] = ("text", "image", "video")
"""目录一级的展示顺序。"""

CAPABILITY_NAMES: dict[str, str] = {
    "text": "文本生成",
    "image": "图片生成",
    "video": "视频生成",
}
"""能力展示名，随请求语言翻译。"""

FAMILIES: dict[str, str] = {
    "minimax": "MiniMax",
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "google": "Google",
    "qwen": "通义千问",
    "wan": "通义万相",
    "volcengine": "火山引擎",
}
"""模型族登记表：键为族标识，值为展示名（随请求语言翻译）。

族按模型产品线划分：豆包归属火山引擎，因此各族标识取品牌归属而不是单个模型名。
新增族在此登记一行即可，未登记的族标识会原样作为展示名，避免文档整页打不开。
"""


@dataclass(frozen=True)
class DocumentedEntry:
    """目录第三级的一个条目。

    ``slug`` 是稳定路由标识；``name`` 是展示名——视频能力下为对外模型名，文本与图片能力下为
    调用形态名；``family_id`` 是该条目所属的模型族，取值必须登记在 ``FAMILIES`` 中；
    ``template_ids`` 按展示顺序列出该条目覆盖的模板，每个模板提供一套参数与示例，端点则由模板与
    能力共同决定。``summary`` 为空时回退首个模板的简介。

    ``form_names`` 按模板声明对外形态名。模板的 ``label`` 带有渠道与实现细节（例如
    ``fal MiniMax H3 Max 文生视频``），在模型节点下既冗余又暴露渠道，因此多形态条目在此给出
    面向调用方的形态名；未声明的模板回退模板 ``label``。
    """

    slug: str
    name: str
    model_type: str
    family_id: str
    template_ids: tuple[str, ...]
    summary: str | None = None
    form_names: dict[str, str] = field(default_factory=dict)


DOCUMENTED_ENTRIES: tuple[DocumentedEntry, ...] = (
    # 视频：条目即对外模型名，同一模型的文生、图生、参考生共用一份文档
    DocumentedEntry(
        slug="minimax-h3-max",
        name="MiniMax H3 Max",
        model_type="video",
        family_id="minimax",
        template_ids=(
            "fal_minimax_h3_max_text_to_video",
            "fal_minimax_h3_max_image_to_video",
            "fal_minimax_h3_max_reference_to_video",
        ),
        summary="支持文生视频、图生视频与参考生视频。",
        form_names={
            "fal_minimax_h3_max_text_to_video": "文生视频",
            "fal_minimax_h3_max_image_to_video": "图生视频",
            "fal_minimax_h3_max_reference_to_video": "参考生视频",
        },
    ),
    DocumentedEntry(
        slug="minimax-h3",
        name="MiniMax H3",
        model_type="video",
        family_id="minimax",
        template_ids=("minimax_h3_default",),
    ),
    DocumentedEntry(
        slug="minimax-h3-official",
        name="MiniMax H3 Official",
        model_type="video",
        family_id="minimax",
        template_ids=("minimax_h3_official_default",),
    ),
    DocumentedEntry(
        slug="openai-video",
        name="OpenAI Video",
        model_type="video",
        family_id="openai",
        template_ids=("openai_video_default",),
    ),
    DocumentedEntry(
        slug="wan-3.0",
        name="wan3.0",
        model_type="video",
        family_id="wan",
        template_ids=("dashscope_video_default",),
    ),
    # 文本与图片：条目即调用形态名，具体可用模型名以 /v1/models 为准
    DocumentedEntry(
        slug="openai-chat",
        name="OpenAI 文本对话",
        model_type="text",
        family_id="openai",
        template_ids=("openai_text_default",),
    ),
    DocumentedEntry(
        slug="openai-responses",
        name="OpenAI Responses",
        model_type="text",
        family_id="openai",
        template_ids=("openai_response_default",),
    ),
    DocumentedEntry(
        slug="anthropic-messages",
        name="Anthropic Messages",
        model_type="text",
        family_id="anthropic",
        template_ids=("anthropic_messages_default",),
    ),
    DocumentedEntry(
        slug="gemini-content",
        name="Gemini 内容生成",
        model_type="text",
        family_id="google",
        template_ids=("gemini_text_default",),
    ),
    DocumentedEntry(
        slug="qwen-generation",
        name="千问文本与多模态生成",
        model_type="text",
        family_id="qwen",
        template_ids=("dashscope_default",),
    ),
    DocumentedEntry(
        slug="doubao-responses",
        name="豆包 Responses",
        model_type="text",
        family_id="volcengine",
        template_ids=("doubao_seed_default",),
    ),
    DocumentedEntry(
        slug="openai-image",
        name="OpenAI 图片生成与编辑",
        model_type="image",
        family_id="openai",
        template_ids=("openai_image_default",),
    ),
    DocumentedEntry(
        slug="gemini-image",
        name="Gemini 图片生成与编辑",
        model_type="image",
        family_id="google",
        template_ids=("gemini_image_default",),
    ),
)


def entries_of(model_type: str) -> tuple[DocumentedEntry, ...]:
    """返回指定能力下的条目，保持声明顺序。"""

    return tuple(entry for entry in DOCUMENTED_ENTRIES if entry.model_type == model_type)


def find_entry(slug: str) -> DocumentedEntry | None:
    """按标识查找条目，未登记时返回空值。"""

    for entry in DOCUMENTED_ENTRIES:
        if entry.slug == slug:
            return entry
    return None


def family_display_name(family_id: str) -> str:
    """返回模型族的展示名原文；未登记的族标识原样返回，保证文档仍可打开。"""

    return FAMILIES.get(family_id, family_id)
