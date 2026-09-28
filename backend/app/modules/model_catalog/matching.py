"""模型名归一化与厂商回退推断。

归一化把模型名收敛为可比较的稳定形式，使同一模型的规范名、带日期后缀的历史名与
大小写、分隔符差异都能命中同一条目录条目。回退推断只在目录未命中时使用，按名称前缀
判断厂商并返回该厂商对应能力的默认模板。
"""

import re

_SEPARATOR_PATTERN = re.compile(r"[-_.]+")
_SUFFIX_MARKER_PATTERN = re.compile(r"[:@].*$")
_DATE_SUFFIX_PATTERN = re.compile(r"-\d{8}$|-\d{4}-\d{2}-\d{2}$")
_DECORATION_SUFFIXES = ("-latest", "-preview", "-free")

_VENDOR_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^(?:gpt-|chatgpt-|codex-|o[1-9](?:-|$)|sora-)"), "openai"),
    (re.compile(r"^claude-"), "anthropic"),
    (re.compile(r"^gemini-"), "google"),
    (re.compile(r"^qwen"), "qwen"),
    (re.compile(r"^doubao-"), "doubao"),
)

# 能力关键词只在名称中显式出现时生效，否则按该厂商的默认能力（文本）处理。
_CAPABILITY_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"image|imagen"), "image"),
    (re.compile(r"video|sora|veo"), "video"),
)

_FALLBACK_TEMPLATES: dict[tuple[str, str], str] = {
    ("openai", "text"): "openai_text_default",
    ("openai", "image"): "openai_image_default",
    ("openai", "video"): "openai_video_default",
    ("anthropic", "text"): "anthropic_messages_default",
    ("google", "text"): "gemini_text_default",
    ("google", "image"): "gemini_image_default",
    ("qwen", "text"): "dashscope_default",
    ("doubao", "text"): "doubao_seed_default",
}

DEFAULT_CAPABILITY = "text"


def normalize_model_name(name: str) -> str:
    """把模型名归一为小写、以连字符分隔、已剥离装饰后缀的形式。

    会剥离 ``:free``、``@日期`` 等标记、八位或 ISO 日期后缀，以及 ``-latest``、``-preview``、
    ``-free`` 装饰后缀；只要还能继续剥离就重复一轮，因此组合后缀也能收敛到同一形式。
    """

    normalized = _SEPARATOR_PATTERN.sub("-", _SUFFIX_MARKER_PATTERN.sub("", name.strip().lower())).strip("-")
    previous = None
    while normalized and normalized != previous:
        previous = normalized
        normalized = _DATE_SUFFIX_PATTERN.sub("", normalized)
        for suffix in _DECORATION_SUFFIXES:
            if normalized.endswith(suffix):
                normalized = normalized[: -len(suffix)]
        normalized = normalized.strip("-")
    return normalized


def match_fallback(normalized_name: str) -> tuple[str, str] | None:
    """按已归一化的模型名推断厂商与能力，返回供应商模板与模型类型。

    能力由名称中的关键词决定，未出现时按文本处理。厂商已识别但该厂商没有对应能力的内置模板
    （例如 Anthropic 与千问没有图片模板）时返回空，交由调用方要求管理员显式指定模板。
    """

    vendor = next((vendor for pattern, vendor in _VENDOR_PATTERNS if pattern.search(normalized_name)), None)
    if vendor is None:
        return None
    capability = next(
        (capability for pattern, capability in _CAPABILITY_PATTERNS if pattern.search(normalized_name)),
        DEFAULT_CAPABILITY,
    )
    template_id = _FALLBACK_TEMPLATES.get((vendor, capability))
    if template_id is None:
        return None
    return template_id, capability
