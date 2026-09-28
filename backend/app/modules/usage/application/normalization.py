from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class NormalizedTextUsage:
    prompt_tokens: int
    completion_tokens: int
    cached_tokens: int
    cache_write_tokens: int
    total_tokens: int | None


@dataclass(frozen=True)
class NormalizedImageUsage:
    input_tokens: int
    output_tokens: int


def normalize_text_usage(payload: dict[str, Any]) -> NormalizedTextUsage | None:
    usage = _usage_payload(payload)
    prompt_tokens = _token_value(usage.get("prompt_tokens"))
    if prompt_tokens is None:
        prompt_tokens = _token_value(usage.get("input_tokens"))
        # Anthropic 的 input_tokens 不含缓存读取与缓存写入，还原为总输入以统一后续计费口径。
        prompt_tokens = _with_cache_tokens(prompt_tokens, usage)
    if prompt_tokens is None:
        prompt_tokens = _token_value(usage.get("promptTokenCount"))
    completion_tokens = _token_value(usage.get("completion_tokens"))
    if completion_tokens is None:
        completion_tokens = _token_value(usage.get("output_tokens"))
    if completion_tokens is None:
        # Gemini 的输出价包含思考 token，而 candidatesTokenCount 不含，需要合并两者。
        completion_tokens = _include_thinking_tokens(usage.get("candidatesTokenCount"), usage)
    if prompt_tokens is None or completion_tokens is None:
        return None
    return NormalizedTextUsage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cached_tokens=_cached_tokens(usage),
        cache_write_tokens=_cache_write_tokens(usage),
        total_tokens=_total_tokens(usage),
    )


def normalize_image_usage(payload: dict[str, Any]) -> NormalizedImageUsage | None:
    usage = _usage_payload(payload)
    input_tokens = _token_value(usage.get("input_tokens"))
    if input_tokens is None:
        input_tokens = _token_value(usage.get("promptTokenCount"))
    output_tokens = _token_value(usage.get("output_tokens"))
    if output_tokens is None:
        # Gemini 的图片输出价同样包含思考 token。
        output_tokens = _include_thinking_tokens(usage.get("candidatesTokenCount"), usage)
    if input_tokens is None or output_tokens is None:
        return None
    return NormalizedImageUsage(input_tokens=input_tokens, output_tokens=output_tokens)


def _usage_payload(payload: dict[str, Any]) -> dict[str, Any]:
    usage = payload.get("usage")
    if isinstance(usage, dict):
        metadata = usage.get("usageMetadata")
        return {**metadata, **usage} if isinstance(metadata, dict) else usage
    metadata = payload.get("usageMetadata")
    return metadata if isinstance(metadata, dict) else payload


def _include_thinking_tokens(candidates: object, usage: dict[str, Any]) -> int | None:
    """把 Gemini 的思考 token 计入输出。

    Gemini 的输出价包含思考 token，而 ``candidatesTokenCount`` 只统计可见输出，
    思考量单独记在 ``thoughtsTokenCount``。主计量缺失时返回空，避免把思考量当成完整输出。
    """

    base = _token_value(candidates)
    if base is None:
        return None
    return base + (_token_value(usage.get("thoughtsTokenCount")) or 0)


def _with_cache_tokens(prompt_tokens: int | None, usage: dict[str, Any]) -> int | None:
    """把 Anthropic 风格的分项输入 token 还原为总输入。

    Anthropic 的 ``input_tokens`` 只统计未命中缓存的输入，缓存读取与缓存写入分别记在
    ``cache_read_input_tokens`` 与 ``cache_creation_input_tokens``。两者都不存在时原样返回。
    """

    cache_read = _token_value(usage.get("cache_read_input_tokens"))
    cache_creation = _token_value(usage.get("cache_creation_input_tokens"))
    if cache_read is None and cache_creation is None:
        return prompt_tokens
    return (prompt_tokens or 0) + (cache_read or 0) + (cache_creation or 0)


def _cached_tokens(usage: dict[str, Any]) -> int:
    prompt_details = usage.get("prompt_tokens_details")
    cached_tokens = prompt_details.get("cached_tokens") if isinstance(prompt_details, dict) else None
    if cached_tokens is None:
        input_details = usage.get("input_tokens_details")
        cached_tokens = input_details.get("cached_tokens") if isinstance(input_details, dict) else None
    if cached_tokens is None:
        cached_tokens = usage.get("cachedContentTokenCount")
    if cached_tokens is None:
        cached_tokens = usage.get("cache_read_input_tokens")
    return _token_value(cached_tokens) or 0


def _cache_write_tokens(usage: dict[str, Any]) -> int:
    """读取缓存写入输入 token。

    OpenAI 在 ``prompt_tokens_details`` / ``input_tokens_details`` 的 ``cache_write_tokens`` 上报，
    Anthropic 在 ``cache_creation_input_tokens`` 上报；其余厂商不上报，按 0 计。
    """

    prompt_details = usage.get("prompt_tokens_details")
    cache_write_tokens = prompt_details.get("cache_write_tokens") if isinstance(prompt_details, dict) else None
    if cache_write_tokens is None:
        input_details = usage.get("input_tokens_details")
        cache_write_tokens = input_details.get("cache_write_tokens") if isinstance(input_details, dict) else None
    if cache_write_tokens is None:
        cache_write_tokens = usage.get("cache_creation_input_tokens")
    return _token_value(cache_write_tokens) or 0


def _total_tokens(usage: dict[str, Any]) -> int | None:
    total_tokens = _token_value(usage.get("total_tokens"))
    if total_tokens is not None:
        return total_tokens
    return _token_value(usage.get("totalTokenCount"))


def _token_value(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value
