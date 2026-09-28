"""公开模型模板的调用端点与鉴权投影。

按公开模型模板推导客户端可见的端点清单，供模型广场与接口文档共用。两处必须给出同一份端点，
因此映射集中在此模块维护；端点取值来自 ``registry`` 中登记的公开协议操作，不新增对外路径。
"""

from typing import Any

BEARER_API_KEY_AUTH: dict[str, str] = {
    "type": "bearer_api_key",
    "header": "Authorization",
    "format": "Bearer <platform_api_key>",
}
"""公开协议面统一的鉴权方式：请求头携带平台访问令牌。"""


def model_operations(*, template_id: str | None, model_type: str) -> list[dict[str, Any]]:
    """返回模板对应的公开调用端点，未收录的模板返回空列表。

    参数：
        template_id: 模型绑定的公开模板标识，为空表示该模型没有明确模板。
        model_type: 模型能力类型，用于区分同一模板下的端点分派。
    返回：
        端点描述列表，每项含协议标识、HTTP 方法、路径、请求编码与鉴权方式；流式端点额外带 ``stream``。
    """

    return [
        {
            "protocol_id": protocol_id,
            "method": method,
            "path": path,
            "content_type": content_type,
            "auth": BEARER_API_KEY_AUTH["type"],
            **({"stream": stream} if stream is not None else {}),
        }
        for protocol_id, method, path, content_type, stream in _operation_specs(
            template_id=template_id, model_type=model_type
        )
    ]


def _operation_specs(*, template_id: str | None, model_type: str) -> list[tuple[str, str, str, str, str | None]]:
    """返回 ``(协议标识, 方法, 路径, 请求编码, 流式)`` 形式的端点原始声明，未收录时为空列表。

    ``流式`` 为 ``None`` 表示该端点不涉及流式；``request`` 表示流式由请求体的 ``stream`` 字段决定；
    ``always`` 表示该端点本身始终流式。
    """

    if template_id == "openai_text_default" and model_type == "text":
        return [("openai_text", "POST", "/v1/chat/completions", "application/json", "request")]
    if template_id == "openai_response_default" and model_type == "text":
        return [("openai_response", "POST", "/v1/responses", "application/json", "request")]
    if template_id == "openai_image_default" and model_type == "image":
        return [
            ("openai_image", "POST", "/v1/images/generations", "application/json", None),
            ("openai_image", "POST", "/v1/images/edits", "multipart/form-data", None),
        ]
    if model_type == "video":
        return [
            ("openai_video", "POST", "/v1/videos", "application/json", None),
            ("openai_video", "GET", "/v1/videos/{video_id}", "application/json", None),
            ("openai_video", "GET", "/v1/videos/{video_id}/content", "video/*", None),
        ]
    if template_id in {"gemini_text_default", "gemini_image_default"} and model_type in {"text", "image"}:
        return [
            ("gemini_text", "POST", "/v1beta/models/{model}:generateContent", "application/json", None),
            ("gemini_text", "POST", "/v1beta/models/{model}:streamGenerateContent", "text/event-stream", "always"),
        ]
    if template_id == "anthropic_messages_default" and model_type == "text":
        return [("anthropic_messages", "POST", "/v1/messages", "application/json", "request")]
    if template_id == "dashscope_default" and model_type == "text":
        return [
            (
                "dashscope_text",
                "POST",
                "/api/v1/services/aigc/text-generation/generation",
                "application/json",
                "request",
            ),
            (
                "dashscope_multimodal",
                "POST",
                "/api/v1/services/aigc/multimodal-generation/generation",
                "application/json",
                "request",
            ),
        ]
    if template_id == "doubao_seed_default" and model_type == "text":
        return [("ark_responses", "POST", "/api/v3/responses", "application/json", "request")]
    return []
