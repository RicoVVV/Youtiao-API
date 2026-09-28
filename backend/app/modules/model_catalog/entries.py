"""内置模型价格目录的数据定义。

本模块只声明目录条目结构与三家厂商的常量数据，不承载匹配、查询或播种逻辑。
所有单价取自厂商官方定价页的标准档位与短上下文档，单位为该厂商官方计价币种；
条目附官方来源链接与价格核对日期，便于后续人工复核与调整。
"""

from dataclasses import dataclass, field

OPENAI_SOURCE_URL = "https://developers.openai.com/api/docs/pricing"
ANTHROPIC_SOURCE_URL = "https://platform.claude.com/docs/en/about-claude/pricing"
GOOGLE_SOURCE_URL = "https://ai.google.dev/gemini-api/docs/pricing"

PRICE_UPDATED_AT = "2026-09-16"

_NO_CACHE_WRITE_NOTE = "官方未提供缓存写入单价，写入项按 0 播种"
_NO_CACHED_INPUT_NOTE = "官方未提供缓存命中输入单价，命中项按 0 播种"
_GEMINI_NO_CACHE_WRITE_NOTE = "Gemini 上下文缓存按小时收存储费，不单独计缓存写入，写入项按 0 播种"
_GEMINI_PROMOTION_NOTE = "促销价，2027-01-01 起涨为输入 1.50 / 缓存命中 0.15 / 输出 7.50"


@dataclass(frozen=True)
class ModelPricingEntry:
    """目录中的单个模型价格条目。

    ``input_price`` / ``cache_write_price`` / ``cached_input_price`` / ``output_price`` 均为
    每百万 token 单价；``aliases`` 补充可命中该条目的其他模型名，带日期后缀的历史名由名称
    归一化统一处理，无需逐一登记。

    ``long_context_threshold`` 为短上下文档的输入 token 上限（含）：请求输入 token 数超过该值时
    整单按长档计价，因此播种出的修正项条件为 ``prompt_tokens >= 阈值 + 1``。为 ``None`` 表示该
    模型不区分上下文档位，或官方未公开阈值。
    """

    canonical_name: str
    template_id: str
    model_type: str
    input_price: str | None = None
    cache_write_price: str | None = None
    cached_input_price: str | None = None
    output_price: str | None = None
    aliases: tuple[str, ...] = field(default_factory=tuple)
    currency: str = "USD"
    source_url: str = ""
    price_updated_at: str = PRICE_UPDATED_AT
    long_context_threshold: int | None = None
    long_context_input_multiplier: str | None = None
    long_context_output_multiplier: str | None = None
    input_image_tokens_per_image: str | None = None
    output_image_tokens_per_image: str | None = None
    text_chars_per_token: str | None = None
    gemini_unknown_image_tiles_per_image: str | None = None
    note: str | None = None

    def search_names(self) -> tuple[str, ...]:
        """返回参与匹配的全部名称，规范名在首位。"""

        return (self.canonical_name, *self.aliases)

    def input_image_estimate_config(self) -> dict[str, str]:
        """图片输入 token 计费项的估算参数；三项校验要求的参数缺一不可。"""

        return {
            "input_image_tokens_per_image": str(self.input_image_tokens_per_image),
            "text_chars_per_token": str(self.text_chars_per_token),
            "gemini_unknown_image_tiles_per_image": str(self.gemini_unknown_image_tiles_per_image),
        }

    def output_image_estimate_config(self) -> dict[str, str]:
        """图片输出 token 计费项的估算参数。"""

        return {"output_image_tokens_per_image": str(self.output_image_tokens_per_image)}


def _openai(
    canonical_name: str,
    *,
    input_price: str,
    cached_input_price: str,
    output_price: str,
    cache_write_price: str = "0.000000",
    aliases: tuple[str, ...] = (),
    long_context_threshold: int | None = None,
    long_context_input_multiplier: str | None = None,
    long_context_output_multiplier: str | None = None,
    note: str | None = None,
) -> ModelPricingEntry:
    return ModelPricingEntry(
        canonical_name=canonical_name,
        template_id="openai_text_default",
        model_type="text",
        input_price=input_price,
        cache_write_price=cache_write_price,
        cached_input_price=cached_input_price,
        output_price=output_price,
        aliases=aliases,
        source_url=OPENAI_SOURCE_URL,
        long_context_threshold=long_context_threshold,
        long_context_input_multiplier=long_context_input_multiplier,
        long_context_output_multiplier=long_context_output_multiplier,
        note=note,
    )


def _anthropic(
    canonical_name: str,
    *,
    input_price: str,
    cache_write_price: str,
    cached_input_price: str,
    output_price: str,
    aliases: tuple[str, ...] = (),
) -> ModelPricingEntry:
    return ModelPricingEntry(
        canonical_name=canonical_name,
        template_id="anthropic_messages_default",
        model_type="text",
        input_price=input_price,
        cache_write_price=cache_write_price,
        cached_input_price=cached_input_price,
        output_price=output_price,
        aliases=aliases,
        source_url=ANTHROPIC_SOURCE_URL,
    )


def _google(
    canonical_name: str,
    *,
    input_price: str,
    cached_input_price: str,
    output_price: str,
    long_context_threshold: int | None = None,
    long_context_input_multiplier: str | None = None,
    long_context_output_multiplier: str | None = None,
    note: str | None = _GEMINI_NO_CACHE_WRITE_NOTE,
) -> ModelPricingEntry:
    return ModelPricingEntry(
        canonical_name=canonical_name,
        template_id="gemini_text_default",
        model_type="text",
        input_price=input_price,
        cache_write_price="0.000000",
        cached_input_price=cached_input_price,
        output_price=output_price,
        source_url=GOOGLE_SOURCE_URL,
        long_context_threshold=long_context_threshold,
        long_context_input_multiplier=long_context_input_multiplier,
        long_context_output_multiplier=long_context_output_multiplier,
        note=note,
    )


_IMAGE_PRICING_SCOPE_NOTE = (
    "官方对图片与文本分开计价，而平台图片 token 计费只有一个输入价与一个输出价，此处取图片价；文本 token 会按图片价计费"
)
_OPENAI_IMAGE_INPUT_TOKENS_PER_IMAGE = "630"
_GEMINI_IMAGE_INPUT_TOKENS_PER_IMAGE = "1032"
_IMAGE_OUTPUT_TOKENS_PER_IMAGE = "1117"
_IMAGE_TEXT_CHARS_PER_TOKEN = "2"
_GEMINI_UNKNOWN_IMAGE_TILES_PER_IMAGE = "4"
_OPENAI_IMAGE_ESTIMATE_NOTE = (
    "估算参数按 OpenAI 官方图片计价口径折算：1024×1024 图约 4 个 512×512 瓦片，"
    f"每张图 {_OPENAI_IMAGE_INPUT_TOKENS_PER_IMAGE} 输入 token；每张输出图 {_IMAGE_OUTPUT_TOKENS_PER_IMAGE} token"
    "。仅在响应未上报用量时用于估算"
)
_GEMINI_IMAGE_ESTIMATE_NOTE = (
    "估算参数按 Gemini 官方图片计价口径折算：1024×1024 图约 4 个 768×768 瓦片（每瓦片 258 token），"
    f"每张图 {_GEMINI_IMAGE_INPUT_TOKENS_PER_IMAGE} 输入 token；每张输出图 {_IMAGE_OUTPUT_TOKENS_PER_IMAGE} token"
    "（按官方每张 1K 图 $0.067 与图片输出 token 单价 $60/1M 反算）。仅在响应未上报用量时用于估算"
)
_OPENAI_IMAGE_25_NOTE = (
    "官方未提供名为 gpt-image-2.5 的单一模型，2.5 代分为 flare（默认选型）与 sunburst（精修档）"
    "两个变体，二者单价一致且与 gpt-image-2 相同"
)
_GEMINI_LITE_IMAGE_ESTIMATE_NOTE = (
    "估算参数与 Gemini 3.1 Flash Image 相同：同尺寸图片的 token 数由图片本身决定，与单价档位无关；"
    "每张输出图 token 数已用官方 1K 图 $0.034 与图片输出 token 单价 $30/1M 交叉核对。仅在响应未上报用量时用于估算"
)
_GEMINI_200K_TIER_NOTE = "长上下文为输入 4.00 / 缓存命中 0.40 / 输出 18.00，阈值为输入超过 200K"


def _image(
    canonical_name: str,
    *,
    template_id: str,
    source_url: str,
    input_price: str,
    output_price: str,
    input_image_tokens_per_image: str,
    note: str,
    aliases: tuple[str, ...] = (),
) -> ModelPricingEntry:
    return ModelPricingEntry(
        canonical_name=canonical_name,
        template_id=template_id,
        model_type="image",
        input_price=input_price,
        output_price=output_price,
        aliases=aliases,
        source_url=source_url,
        input_image_tokens_per_image=input_image_tokens_per_image,
        output_image_tokens_per_image=_IMAGE_OUTPUT_TOKENS_PER_IMAGE,
        text_chars_per_token=_IMAGE_TEXT_CHARS_PER_TOKEN,
        gemini_unknown_image_tiles_per_image=_GEMINI_UNKNOWN_IMAGE_TILES_PER_IMAGE,
        note=note,
    )


_OPENAI_5_6_PRICE_NOTE = "价格取自官方定价页当前值（GPT-5.6 Sol 为促销价，官方称至少持续到 2026-11-21）"
_OPENAI_6_PRICE_NOTE = "价格取自官方 GPT-6 模型文档的文本 token 标准档，2026-09-23 核对"
_OPENAI_LONG_CONTEXT_NOTE = "长上下文：输入超过 272K 时整单按输入类 ×2、输出 ×1.5 计价，已播种分档加价"
_OPENAI_INFERRED_THRESHOLD_NOTE = "该系列的档位阈值官方未单独写明，按 OpenAI 旗舰家族统一的 272K 处理"
_OPENAI_4_1_FLAT_NOTE = "GPT-4.1 系列在完整 1M 窗口内为单一档位，官方未设长上下文加价"

OPENAI_ENTRIES: tuple[ModelPricingEntry, ...] = (
    _openai(
        "gpt-5.6-sol",
        input_price="4.000000",
        cache_write_price="5.000000",
        cached_input_price="0.400000",
        output_price="20.000000",
        long_context_threshold=272000,
        long_context_input_multiplier="2.000000",
        long_context_output_multiplier="1.500000",
        note=f"{_OPENAI_5_6_PRICE_NOTE}；{_OPENAI_LONG_CONTEXT_NOTE}",
    ),
    _openai(
        "gpt-5.6-terra",
        input_price="2.000000",
        cache_write_price="2.500000",
        cached_input_price="0.200000",
        output_price="12.000000",
        long_context_threshold=272000,
        long_context_input_multiplier="2.000000",
        long_context_output_multiplier="1.500000",
        note=f"{_OPENAI_5_6_PRICE_NOTE}；{_OPENAI_LONG_CONTEXT_NOTE}",
    ),
    _openai(
        "gpt-5.6-luna",
        input_price="0.200000",
        cache_write_price="0.250000",
        cached_input_price="0.020000",
        output_price="1.200000",
        long_context_threshold=272000,
        long_context_input_multiplier="2.000000",
        long_context_output_multiplier="1.500000",
        note=f"{_OPENAI_5_6_PRICE_NOTE}；{_OPENAI_LONG_CONTEXT_NOTE}",
    ),
    _openai(
        "gpt-5.5",
        input_price="5.000000",
        cached_input_price="0.500000",
        output_price="30.000000",
        long_context_threshold=272000,
        long_context_input_multiplier="2.000000",
        long_context_output_multiplier="1.500000",
        note=f"{_NO_CACHE_WRITE_NOTE}；{_OPENAI_LONG_CONTEXT_NOTE}；{_OPENAI_INFERRED_THRESHOLD_NOTE}",
    ),
    _openai(
        "gpt-5.5-pro",
        input_price="30.000000",
        cached_input_price="0.000000",
        output_price="180.000000",
        long_context_threshold=272000,
        long_context_input_multiplier="2.000000",
        long_context_output_multiplier="1.500000",
        note=(
            f"{_NO_CACHE_WRITE_NOTE}；{_NO_CACHED_INPUT_NOTE}；"
            f"{_OPENAI_LONG_CONTEXT_NOTE}；{_OPENAI_INFERRED_THRESHOLD_NOTE}"
        ),
    ),
    _openai(
        "gpt-5.4",
        input_price="2.500000",
        cached_input_price="0.250000",
        output_price="15.000000",
        long_context_threshold=272000,
        long_context_input_multiplier="2.000000",
        long_context_output_multiplier="1.500000",
        note=f"{_NO_CACHE_WRITE_NOTE}；{_OPENAI_LONG_CONTEXT_NOTE}；{_OPENAI_INFERRED_THRESHOLD_NOTE}",
    ),
    _openai(
        "gpt-5.4-mini",
        input_price="0.750000",
        cached_input_price="0.075000",
        output_price="4.500000",
        note=_NO_CACHE_WRITE_NOTE,
    ),
    _openai(
        "gpt-5.4-nano",
        input_price="0.200000",
        cached_input_price="0.020000",
        output_price="1.250000",
        note=_NO_CACHE_WRITE_NOTE,
    ),
    _openai(
        "gpt-5.4-pro",
        input_price="30.000000",
        cached_input_price="0.000000",
        output_price="180.000000",
        long_context_threshold=272000,
        long_context_input_multiplier="2.000000",
        long_context_output_multiplier="1.500000",
        note=(
            f"{_NO_CACHE_WRITE_NOTE}；{_NO_CACHED_INPUT_NOTE}；"
            f"{_OPENAI_LONG_CONTEXT_NOTE}；{_OPENAI_INFERRED_THRESHOLD_NOTE}"
        ),
    ),
    _openai(
        "gpt-5.3-codex",
        input_price="1.750000",
        cached_input_price="0.175000",
        output_price="14.000000",
        note=_NO_CACHE_WRITE_NOTE,
    ),
    _openai(
        "gpt-5.3-chat-latest",
        input_price="1.750000",
        cached_input_price="0.175000",
        output_price="14.000000",
        aliases=("chat-latest",),
        note=_NO_CACHE_WRITE_NOTE,
    ),
    _openai(
        "gpt-6-astra",
        input_price="10.000000",
        cache_write_price="12.500000",
        cached_input_price="1.000000",
        output_price="50.000000",
        long_context_threshold=272000,
        long_context_input_multiplier="2.000000",
        long_context_output_multiplier="1.500000",
        note="官方定价表尚未收录该模型，价格来自发布费率卡；长上下文为输入 20.00 / 缓存写入 25.00 / 缓存命中 2.00 / 输出 75.00，阈值为输入超过 272K",
    ),
    _openai(
        "gpt-6-sol",
        input_price="2.000000",
        cache_write_price="2.500000",
        cached_input_price="0.200000",
        output_price="10.000000",
        long_context_threshold=272000,
        long_context_input_multiplier="2.000000",
        long_context_output_multiplier="1.500000",
        note=f"{_OPENAI_6_PRICE_NOTE}；{_OPENAI_LONG_CONTEXT_NOTE}",
    ),
    _openai(
        "gpt-6-luna",
        input_price="0.100000",
        cache_write_price="0.125000",
        cached_input_price="0.010000",
        output_price="0.500000",
        long_context_threshold=272000,
        long_context_input_multiplier="2.000000",
        long_context_output_multiplier="1.500000",
        note=f"{_OPENAI_6_PRICE_NOTE}；{_OPENAI_LONG_CONTEXT_NOTE}",
    ),
    _openai(
        "gpt-5",
        input_price="1.250000",
        cached_input_price="0.125000",
        output_price="10.000000",
        note=_NO_CACHE_WRITE_NOTE,
    ),
    _openai(
        "gpt-5-mini",
        input_price="0.250000",
        cached_input_price="0.025000",
        output_price="2.000000",
        note=_NO_CACHE_WRITE_NOTE,
    ),
    _openai(
        "gpt-5-nano",
        input_price="0.050000",
        cached_input_price="0.005000",
        output_price="0.400000",
        note=_NO_CACHE_WRITE_NOTE,
    ),
    _openai(
        "gpt-4.1",
        input_price="2.000000",
        cached_input_price="0.500000",
        output_price="8.000000",
        note=f"{_NO_CACHE_WRITE_NOTE}；{_OPENAI_4_1_FLAT_NOTE}",
    ),
    _openai(
        "gpt-4.1-mini",
        input_price="0.400000",
        cached_input_price="0.100000",
        output_price="1.600000",
        note=f"{_NO_CACHE_WRITE_NOTE}；{_OPENAI_4_1_FLAT_NOTE}",
    ),
    _openai(
        "gpt-4.1-nano",
        input_price="0.100000",
        cached_input_price="0.025000",
        output_price="0.400000",
        note=f"{_NO_CACHE_WRITE_NOTE}；{_OPENAI_4_1_FLAT_NOTE}",
    ),
    _openai(
        "gpt-4o",
        input_price="2.500000",
        cached_input_price="1.250000",
        output_price="10.000000",
        note=_NO_CACHE_WRITE_NOTE,
    ),
    _openai(
        "gpt-4o-mini",
        input_price="0.150000",
        cached_input_price="0.075000",
        output_price="0.600000",
        note=_NO_CACHE_WRITE_NOTE,
    ),
    _openai(
        "o3",
        input_price="2.000000",
        cached_input_price="0.500000",
        output_price="8.000000",
        note=_NO_CACHE_WRITE_NOTE,
    ),
    _openai(
        "o3-mini",
        input_price="1.100000",
        cached_input_price="0.550000",
        output_price="4.400000",
        note=_NO_CACHE_WRITE_NOTE,
    ),
    _openai(
        "o4-mini",
        input_price="1.100000",
        cached_input_price="0.275000",
        output_price="4.400000",
        note=_NO_CACHE_WRITE_NOTE,
    ),
    _openai(
        "gpt-5.2",
        input_price="1.750000",
        cached_input_price="0.175000",
        output_price="14.000000",
        note=_NO_CACHE_WRITE_NOTE,
    ),
    _openai(
        "gpt-5.1",
        input_price="1.250000",
        cached_input_price="0.125000",
        output_price="10.000000",
        note=_NO_CACHE_WRITE_NOTE,
    ),
    _openai(
        "gpt-5-pro",
        input_price="15.000000",
        cached_input_price="0.000000",
        output_price="120.000000",
        note=f"{_NO_CACHE_WRITE_NOTE}；{_NO_CACHED_INPUT_NOTE}",
    ),
    _openai(
        "gpt-4-turbo",
        input_price="10.000000",
        cached_input_price="0.000000",
        output_price="30.000000",
        note=f"{_NO_CACHE_WRITE_NOTE}；{_NO_CACHED_INPUT_NOTE}",
    ),
    _openai(
        "o3-pro",
        input_price="20.000000",
        cached_input_price="0.000000",
        output_price="80.000000",
        note=f"{_NO_CACHE_WRITE_NOTE}；{_NO_CACHED_INPUT_NOTE}",
    ),
    _openai(
        "o1",
        input_price="15.000000",
        cached_input_price="7.500000",
        output_price="60.000000",
        note=_NO_CACHE_WRITE_NOTE,
    ),
)

ANTHROPIC_ENTRIES: tuple[ModelPricingEntry, ...] = (
    _anthropic(
        "claude-fable-5-1",
        input_price="10.000000",
        cache_write_price="12.500000",
        cached_input_price="0.250000",
        output_price="50.000000",
    ),
    _anthropic(
        "claude-fable-5",
        input_price="10.000000",
        cache_write_price="12.500000",
        cached_input_price="1.000000",
        output_price="50.000000",
    ),
    _anthropic(
        "claude-mythos-5-1",
        input_price="10.000000",
        cache_write_price="12.500000",
        cached_input_price="0.250000",
        output_price="50.000000",
    ),
    _anthropic(
        "claude-mythos-5",
        input_price="10.000000",
        cache_write_price="12.500000",
        cached_input_price="1.000000",
        output_price="50.000000",
    ),
    _anthropic(
        "claude-opus-5-5",
        input_price="4.000000",
        cache_write_price="5.000000",
        cached_input_price="0.200000",
        output_price="20.000000",
    ),
    _anthropic(
        "claude-opus-5",
        input_price="5.000000",
        cache_write_price="6.250000",
        cached_input_price="0.500000",
        output_price="25.000000",
    ),
    _anthropic(
        "claude-opus-4-8",
        input_price="5.000000",
        cache_write_price="6.250000",
        cached_input_price="0.500000",
        output_price="25.000000",
    ),
    _anthropic(
        "claude-opus-4-7",
        input_price="5.000000",
        cache_write_price="6.250000",
        cached_input_price="0.500000",
        output_price="25.000000",
    ),
    _anthropic(
        "claude-opus-4-6",
        input_price="5.000000",
        cache_write_price="6.250000",
        cached_input_price="0.500000",
        output_price="25.000000",
    ),
    _anthropic(
        "claude-opus-4-5",
        input_price="5.000000",
        cache_write_price="6.250000",
        cached_input_price="0.500000",
        output_price="25.000000",
    ),
    _anthropic(
        "claude-opus-4-1",
        input_price="15.000000",
        cache_write_price="18.750000",
        cached_input_price="1.500000",
        output_price="75.000000",
    ),
    _anthropic(
        "claude-opus-4",
        input_price="15.000000",
        cache_write_price="18.750000",
        cached_input_price="1.500000",
        output_price="75.000000",
    ),
    _anthropic(
        "claude-sonnet-5",
        input_price="2.000000",
        cache_write_price="2.500000",
        cached_input_price="0.200000",
        output_price="10.000000",
    ),
    _anthropic(
        "claude-sonnet-4-6",
        input_price="3.000000",
        cache_write_price="3.750000",
        cached_input_price="0.300000",
        output_price="15.000000",
    ),
    _anthropic(
        "claude-sonnet-4-5",
        input_price="3.000000",
        cache_write_price="3.750000",
        cached_input_price="0.300000",
        output_price="15.000000",
    ),
    _anthropic(
        "claude-sonnet-4",
        input_price="3.000000",
        cache_write_price="3.750000",
        cached_input_price="0.300000",
        output_price="15.000000",
    ),
    _anthropic(
        "claude-haiku-4-5",
        input_price="1.000000",
        cache_write_price="1.250000",
        cached_input_price="0.100000",
        output_price="5.000000",
    ),
    _anthropic(
        "claude-haiku-3-5",
        input_price="0.800000",
        cache_write_price="1.000000",
        cached_input_price="0.080000",
        output_price="4.000000",
        aliases=("claude-3-5-haiku",),
    ),
    _anthropic(
        "claude-3-7-sonnet",
        input_price="3.000000",
        cache_write_price="3.750000",
        cached_input_price="0.300000",
        output_price="15.000000",
    ),
    _anthropic(
        "claude-3-5-sonnet",
        input_price="3.000000",
        cache_write_price="3.750000",
        cached_input_price="0.300000",
        output_price="15.000000",
    ),
    _anthropic(
        "claude-3-opus",
        input_price="15.000000",
        cache_write_price="18.750000",
        cached_input_price="1.500000",
        output_price="75.000000",
    ),
    _anthropic(
        "claude-3-haiku",
        input_price="0.250000",
        cache_write_price="0.300000",
        cached_input_price="0.030000",
        output_price="1.250000",
    ),
)

GOOGLE_ENTRIES: tuple[ModelPricingEntry, ...] = (
    _google(
        "gemini-3.8-flash",
        input_price="0.750000",
        cached_input_price="0.075000",
        output_price="3.750000",
        note=f"{_GEMINI_NO_CACHE_WRITE_NOTE}；{_GEMINI_PROMOTION_NOTE}",
    ),
    _google(
        "gemini-3.7-flash",
        input_price="0.750000",
        cached_input_price="0.075000",
        output_price="3.750000",
        note=f"{_GEMINI_NO_CACHE_WRITE_NOTE}；{_GEMINI_PROMOTION_NOTE}",
    ),
    _google(
        "gemini-3.6-flash",
        input_price="0.750000",
        cached_input_price="0.075000",
        output_price="3.750000",
        note=f"{_GEMINI_NO_CACHE_WRITE_NOTE}；{_GEMINI_PROMOTION_NOTE}",
    ),
    _google(
        "gemini-3.5-flash",
        input_price="1.500000",
        cached_input_price="0.150000",
        output_price="9.000000",
    ),
    _google(
        "gemini-3.5-flash-lite",
        input_price="0.300000",
        cached_input_price="0.030000",
        output_price="2.500000",
    ),
    _google(
        "gemini-3.1-flash-lite",
        input_price="0.250000",
        cached_input_price="0.025000",
        output_price="1.500000",
    ),
    _google(
        "gemini-3.1-pro-preview",
        input_price="2.000000",
        cached_input_price="0.200000",
        output_price="12.000000",
        long_context_threshold=200000,
        long_context_input_multiplier="2.000000",
        long_context_output_multiplier="1.500000",
        note=f"{_GEMINI_NO_CACHE_WRITE_NOTE}；{_GEMINI_200K_TIER_NOTE}",
    ),
    _google(
        "gemini-3-pro-preview",
        input_price="2.000000",
        cached_input_price="0.200000",
        output_price="12.000000",
        long_context_threshold=200000,
        long_context_input_multiplier="2.000000",
        long_context_output_multiplier="1.500000",
        note=f"{_GEMINI_NO_CACHE_WRITE_NOTE}；{_GEMINI_200K_TIER_NOTE}",
    ),
    _google(
        "gemini-3-flash-preview",
        input_price="0.500000",
        cached_input_price="0.050000",
        output_price="3.000000",
    ),
    _google(
        "gemini-2.5-pro",
        input_price="1.250000",
        cached_input_price="0.125000",
        output_price="10.000000",
    ),
    _google(
        "gemini-2.5-flash",
        input_price="0.300000",
        cached_input_price="0.030000",
        output_price="2.500000",
    ),
    _google(
        "gemini-2.5-flash-lite",
        input_price="0.100000",
        cached_input_price="0.010000",
        output_price="0.400000",
    ),
    _google(
        "gemini-2.0-flash",
        input_price="0.100000",
        cached_input_price="0.025000",
        output_price="0.400000",
    ),
    _google(
        "gemini-2.0-flash-lite",
        input_price="0.075000",
        cached_input_price="0.018750",
        output_price="0.300000",
    ),
)

IMAGE_ENTRIES: tuple[ModelPricingEntry, ...] = (
    _image(
        "gpt-image-2",
        template_id="openai_image_default",
        source_url=OPENAI_SOURCE_URL,
        input_price="8.000000",
        output_price="30.000000",
        input_image_tokens_per_image=_OPENAI_IMAGE_INPUT_TOKENS_PER_IMAGE,
        note=f"{_IMAGE_PRICING_SCOPE_NOTE}；{_OPENAI_IMAGE_ESTIMATE_NOTE}",
    ),
    _image(
        "gpt-image-2.5-flare",
        template_id="openai_image_default",
        source_url=OPENAI_SOURCE_URL,
        input_price="8.000000",
        output_price="30.000000",
        input_image_tokens_per_image=_OPENAI_IMAGE_INPUT_TOKENS_PER_IMAGE,
        note=f"{_IMAGE_PRICING_SCOPE_NOTE}；{_OPENAI_IMAGE_25_NOTE}；{_OPENAI_IMAGE_ESTIMATE_NOTE}",
        aliases=("gpt-image-2.5",),
    ),
    _image(
        "gpt-image-2.5-sunburst",
        template_id="openai_image_default",
        source_url=OPENAI_SOURCE_URL,
        input_price="8.000000",
        output_price="30.000000",
        input_image_tokens_per_image=_OPENAI_IMAGE_INPUT_TOKENS_PER_IMAGE,
        note=f"{_IMAGE_PRICING_SCOPE_NOTE}；{_OPENAI_IMAGE_25_NOTE}；{_OPENAI_IMAGE_ESTIMATE_NOTE}",
    ),
    _image(
        "gpt-image-1.5",
        template_id="openai_image_default",
        source_url=OPENAI_SOURCE_URL,
        input_price="8.000000",
        output_price="32.000000",
        input_image_tokens_per_image=_OPENAI_IMAGE_INPUT_TOKENS_PER_IMAGE,
        note=f"{_IMAGE_PRICING_SCOPE_NOTE}；{_OPENAI_IMAGE_ESTIMATE_NOTE}",
    ),
    _image(
        "gpt-image-1-mini",
        template_id="openai_image_default",
        source_url=OPENAI_SOURCE_URL,
        input_price="2.500000",
        output_price="8.000000",
        input_image_tokens_per_image=_OPENAI_IMAGE_INPUT_TOKENS_PER_IMAGE,
        note=f"{_IMAGE_PRICING_SCOPE_NOTE}；{_OPENAI_IMAGE_ESTIMATE_NOTE}",
    ),
    _image(
        "gemini-3.1-flash-image",
        template_id="gemini_image_default",
        source_url=GOOGLE_SOURCE_URL,
        input_price="0.500000",
        output_price="60.000000",
        input_image_tokens_per_image=_GEMINI_IMAGE_INPUT_TOKENS_PER_IMAGE,
        note=f"{_IMAGE_PRICING_SCOPE_NOTE}；{_GEMINI_IMAGE_ESTIMATE_NOTE}",
    ),
    _image(
        "gemini-3-pro-image",
        template_id="gemini_image_default",
        source_url=GOOGLE_SOURCE_URL,
        input_price="2.000000",
        output_price="120.000000",
        input_image_tokens_per_image=_GEMINI_IMAGE_INPUT_TOKENS_PER_IMAGE,
        note=f"{_IMAGE_PRICING_SCOPE_NOTE}；{_GEMINI_IMAGE_ESTIMATE_NOTE}",
    ),
    _image(
        "gemini-3.1-flash-lite-image",
        template_id="gemini_image_default",
        source_url=GOOGLE_SOURCE_URL,
        input_price="0.250000",
        output_price="30.000000",
        input_image_tokens_per_image=_GEMINI_IMAGE_INPUT_TOKENS_PER_IMAGE,
        note=f"{_IMAGE_PRICING_SCOPE_NOTE}；{_GEMINI_LITE_IMAGE_ESTIMATE_NOTE}",
    ),
)

CATALOG_ENTRIES: tuple[ModelPricingEntry, ...] = (
    *OPENAI_ENTRIES,
    *ANTHROPIC_ENTRIES,
    *GOOGLE_ENTRIES,
    *IMAGE_ENTRIES,
)
