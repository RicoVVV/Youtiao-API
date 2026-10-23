"""最小探测请求构造。

健康探测与分组嗅探都要向真实渠道发送一条最小文本请求。请求体必须与模型公开模板的协议一致：
OpenAI 协议使用 ``messages``，Gemini 使用 ``contents``，DashScope 使用 ``input.messages``，
豆包只有 Responses 协议。此处按模板集中构造请求体并给出对应的 Provider 调用方法名，
避免探测请求被厂商适配器判为非法而误判为渠道故障。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

_PROBE_MESSAGE = "hi"
_PROBE_MAX_TOKENS = 16


@dataclass(frozen=True, slots=True)
class ProbeRequest:
    """一次最小探测的 Provider 调用方法名与请求体。"""

    operation: str
    body: dict[str, Any]


def build_probe_request(*, template_id: str, model_name: str) -> ProbeRequest | None:
    """按公开模板构造最小文本探测请求；模板未登记探测形状时返回空值。"""

    spec = _PROBE_SPECS.get(template_id)
    if spec is None:
        return None
    operation, build_body = spec
    return ProbeRequest(operation=operation, body={**build_body(), "model": model_name})


def _openai_body() -> dict[str, Any]:
    return {
        "messages": [{"role": "user", "content": _PROBE_MESSAGE}],
        "max_tokens": _PROBE_MAX_TOKENS,
    }


def _gemini_body() -> dict[str, Any]:
    return {
        "contents": [{"role": "user", "parts": [{"text": _PROBE_MESSAGE}]}],
        "generationConfig": {"maxOutputTokens": _PROBE_MAX_TOKENS},
    }


def _dashscope_body() -> dict[str, Any]:
    return {
        "input": {"messages": [{"role": "user", "content": _PROBE_MESSAGE}]},
        "parameters": {"result_format": "message", "max_tokens": _PROBE_MAX_TOKENS},
    }


def _doubao_body() -> dict[str, Any]:
    return {"input": _PROBE_MESSAGE, "max_output_tokens": _PROBE_MAX_TOKENS}


_PROBE_SPECS: dict[str, tuple[str, Callable[[], dict[str, Any]]]] = {
    # Anthropic 原生 Messages 与 OpenAI Chat 形状同键，均走 ``chat``。
    "openai_text_default": ("chat", _openai_body),
    "anthropic_messages_default": ("chat", _openai_body),
    "gemini_text_default": ("chat", _gemini_body),
    "dashscope_default": ("chat", _dashscope_body),
    "doubao_seed_default": ("create_response", _doubao_body),
}
