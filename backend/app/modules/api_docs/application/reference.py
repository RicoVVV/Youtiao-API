"""接口文档的公共说明：错误体形状、错误码与视频任务状态。

本模块是面向调用方的说明副本，必须与实现保持一致：错误映射以 ``app/web/exception_handlers.py``
为准，视频任务状态以 ``app/modules/video/application/tasks/creation.py`` 的对外投影为准。
改动上述实现时须同步这里的说明。

``status``/``code``/``message`` 取自协议的稳定取值，原样返回不翻译；其余说明文案按平台约定以
中文原文为键，经 ``translate`` 输出目标语言。
"""

from typing import Any

from app.core.i18n import translate

_TOKEN_SCENE = "令牌缺失、无效或已停用"
_BALANCE_SCENE = "账户余额不足"
_FORBIDDEN_SCENE = "令牌无权访问该模型或模型分组"
_NOT_FOUND_SCENE = "请求的资源或任务不存在"
_CONFLICT_SCENE = "请求与现有资源冲突"
_INVALID_SCENE = "请求参数或模型契约校验失败"
_RATE_LIMIT_SCENE = "超出速率或并发限制"
_INTERNAL_SCENE = "服务内部错误"
_UPSTREAM_UNAVAILABLE_SCENE = "上游服务不可用"
_UPSTREAM_TIMEOUT_SCENE = "上游服务超时"
_AUTH_UNAVAILABLE_SCENE = "鉴权服务暂时不可用"

_OPENAI_ENTRIES: tuple[dict[str, Any], ...] = (
    {"status": 401, "code": "invalid_api_key", "message": "Invalid API key", "scene": _TOKEN_SCENE},
    {"status": 402, "code": "insufficient_balance", "message": "Insufficient balance", "scene": _BALANCE_SCENE},
    {
        "status": 403,
        "code": None,
        "message": "Permission denied",
        "scene": _FORBIDDEN_SCENE,
    },
    {"status": 404, "code": "video_not_found", "message": "Video not found", "scene": _NOT_FOUND_SCENE},
    {"status": 404, "code": "not_found", "message": "Resource not found", "scene": _NOT_FOUND_SCENE},
    {
        "status": 409,
        "code": "conflict",
        "message": "Request conflicts with an existing resource",
        "scene": _CONFLICT_SCENE,
    },
    {
        "status": 422,
        "code": "invalid_request_error",
        "message": "Invalid request parameters",
        "scene": _INVALID_SCENE,
    },
    {
        "status": 429,
        "code": "rate_limit_exceeded",
        "message": "Rate limit exceeded",
        "scene": _RATE_LIMIT_SCENE,
    },
    {"status": 500, "code": "internal_error", "message": "Internal server error", "scene": _INTERNAL_SCENE},
    {
        "status": 502,
        "code": "upstream_unavailable",
        "message": "Upstream service unavailable",
        "scene": _UPSTREAM_UNAVAILABLE_SCENE,
    },
    {
        "status": 503,
        "code": "authentication_unavailable",
        "message": "Authentication service temporarily unavailable",
        "scene": _AUTH_UNAVAILABLE_SCENE,
    },
    {
        "status": 504,
        "code": "upstream_timeout",
        "message": "Upstream service timed out",
        "scene": _UPSTREAM_TIMEOUT_SCENE,
    },
)

_ANTHROPIC_ENTRIES: tuple[dict[str, Any], ...] = (
    {"status": 401, "code": "authentication_error", "message": "Invalid API key", "scene": _TOKEN_SCENE},
    {"status": 402, "code": "invalid_request_error", "message": "Insufficient balance", "scene": _BALANCE_SCENE},
    {"status": 403, "code": "permission_error", "message": "Permission denied", "scene": _FORBIDDEN_SCENE},
    {
        "status": 404,
        "code": "invalid_request_error",
        "message": "Resource not found",
        "scene": _NOT_FOUND_SCENE,
    },
    {"status": 409, "code": "invalid_request_error", "message": "Conflict", "scene": _CONFLICT_SCENE},
    {
        "status": 422,
        "code": "invalid_request_error",
        "message": "Invalid request parameters",
        "scene": _INVALID_SCENE,
    },
    {"status": 429, "code": "rate_limit_error", "message": "Rate limit exceeded", "scene": _RATE_LIMIT_SCENE},
    {"status": 500, "code": "api_error", "message": "Internal server error", "scene": _INTERNAL_SCENE},
    {
        "status": 502,
        "code": "api_error",
        "message": "Upstream service unavailable",
        "scene": _UPSTREAM_UNAVAILABLE_SCENE,
    },
    {
        "status": 503,
        "code": "api_error",
        "message": "Authentication service temporarily unavailable",
        "scene": _AUTH_UNAVAILABLE_SCENE,
    },
    {"status": 504, "code": "api_error", "message": "Upstream service timed out", "scene": _UPSTREAM_TIMEOUT_SCENE},
)

_GEMINI_ENTRIES: tuple[dict[str, Any], ...] = (
    {"status": 401, "code": "authentication_error", "message": "Invalid API key", "scene": _TOKEN_SCENE},
    {
        "status": 402,
        "code": "invalid_request_error",
        "message": "Insufficient balance",
        "scene": _BALANCE_SCENE,
    },
    {"status": 403, "code": "permission_error", "message": "Permission denied", "scene": _FORBIDDEN_SCENE},
    {
        "status": 404,
        "code": "invalid_request_error",
        "message": "Resource not found",
        "scene": _NOT_FOUND_SCENE,
    },
    {"status": 409, "code": "invalid_request_error", "message": "Conflict", "scene": _CONFLICT_SCENE},
    {
        "status": 422,
        "code": "invalid_request_error",
        "message": "Invalid request parameters",
        "scene": _INVALID_SCENE,
    },
    {"status": 429, "code": "rate_limit_error", "message": "Rate limit exceeded", "scene": _RATE_LIMIT_SCENE},
    {"status": 500, "code": "server_error", "message": "Internal server error", "scene": _INTERNAL_SCENE},
    {
        "status": 502,
        "code": "server_error",
        "message": "Upstream service unavailable",
        "scene": _UPSTREAM_UNAVAILABLE_SCENE,
    },
    {
        "status": 503,
        "code": "server_error",
        "message": "Authentication service temporarily unavailable",
        "scene": _AUTH_UNAVAILABLE_SCENE,
    },
    {"status": 504, "code": "server_error", "message": "Upstream service timed out", "scene": _UPSTREAM_TIMEOUT_SCENE},
)

_DASHSCOPE_ENTRIES: tuple[dict[str, Any], ...] = (
    {"status": 401, "code": "InvalidApiKey", "message": "Invalid API key", "scene": _TOKEN_SCENE},
    {"status": 402, "code": "Arrearage", "message": "Insufficient balance", "scene": _BALANCE_SCENE},
    {"status": 403, "code": "AccessDenied", "message": "Permission denied", "scene": _FORBIDDEN_SCENE},
    {"status": 404, "code": "ModelNotExist", "message": "Resource not found", "scene": _NOT_FOUND_SCENE},
    {"status": 409, "code": "InvalidParameter", "message": "Conflict", "scene": _CONFLICT_SCENE},
    {"status": 422, "code": "InvalidParameter", "message": "Invalid request parameters", "scene": _INVALID_SCENE},
    {"status": 429, "code": "Throttling", "message": "Rate limit exceeded", "scene": _RATE_LIMIT_SCENE},
    {"status": 500, "code": "InternalError", "message": "Internal server error", "scene": _INTERNAL_SCENE},
    {
        "status": 502,
        "code": "InternalError",
        "message": "Upstream service unavailable",
        "scene": _UPSTREAM_UNAVAILABLE_SCENE,
    },
    {
        "status": 503,
        "code": "InternalError",
        "message": "Authentication service temporarily unavailable",
        "scene": _AUTH_UNAVAILABLE_SCENE,
    },
    {
        "status": 504,
        "code": "RequestTimeout",
        "message": "Upstream service timed out",
        "scene": _UPSTREAM_TIMEOUT_SCENE,
    },
)

ERROR_SHAPES: dict[str, dict[str, Any]] = {
    "openai": {
        "body": {"error": {"message": "...", "type": "...", "param": None, "code": "..."}},
        "entries": _OPENAI_ENTRIES,
    },
    "anthropic": {"body": {"type": "error", "error": {"type": "...", "message": "..."}}, "entries": _ANTHROPIC_ENTRIES},
    "gemini": {"body": {"error": {"code": 422, "message": "...", "status": "..."}}, "entries": _GEMINI_ENTRIES},
    "dashscope": {"body": {"code": "...", "message": "...", "request_id": "..."}, "entries": _DASHSCOPE_ENTRIES},
}
"""错误体形状：``body`` 是响应骨架，``entries`` 是该协议面可能返回的状态码与错误码。"""

PROTOCOL_ERROR_SHAPES: dict[str, str] = {
    "openai_text": "openai",
    "openai_response": "openai",
    "openai_image": "openai",
    "openai_video": "openai",
    "openai_models": "openai",
    # 火山方舟响应路径同样返回 OpenAI 形状，见 exception_handlers 的分派顺序
    "ark_responses": "openai",
    "anthropic_messages": "anthropic",
    "gemini_text": "gemini",
    "dashscope_text": "dashscope",
    "dashscope_multimodal": "dashscope",
}
"""协议标识到错误体形状的映射。"""

_STATUS_DESCRIPTIONS: tuple[tuple[str, str], ...] = (
    ("queued", "任务已受理，等待生成"),
    ("in_progress", "正在生成视频"),
    ("completed", "视频已生成完成，可通过结果地址下载"),
    ("failed", "生成失败或任务被终止，失败原因见 error 字段"),
)

_STATUS_NOTE = "任务状态由平台按上游处理进度推进；仅 completed 提供结果地址，failed 时由 error 字段给出原因。"

_MATERIAL_NOTE = "素材字段既可直接传入公开可访问的 URL，也可随创建请求以 multipart/form-data 上传文件。"

_STREAM_NOTE = "请求体 stream 为 true 时以 SSE 返回增量内容。"

_STREAM_ALWAYS_NOTE = "该接口始终以 SSE 返回增量内容。"


def error_reference(protocol_ids: list[str], locale: str) -> list[dict[str, Any]]:
    """按协议面聚合错误说明，同一形状只出现一次。

    参数：
        protocol_ids: 该条目涉及的协议标识，按出现顺序传入。
        locale: 目标语言。
    返回：
        每项含 ``shape``（形状标识）、``protocol_ids``（使用该形状的协议）、``body``（响应骨架）
        与 ``entries``（状态码、错误码、原始 message 与场景说明）。
    """

    grouped: dict[str, list[str]] = {}
    for protocol_id in protocol_ids:
        shape = PROTOCOL_ERROR_SHAPES.get(protocol_id)
        if shape is None:
            continue
        protocols = grouped.setdefault(shape, [])
        if protocol_id not in protocols:
            protocols.append(protocol_id)
    return [
        {
            "shape": shape,
            "protocol_ids": protocols,
            "body": ERROR_SHAPES[shape]["body"],
            "entries": [
                {**entry, "scene": translate(entry["scene"], locale)} for entry in ERROR_SHAPES[shape]["entries"]
            ],
        }
        for shape, protocols in grouped.items()
    ]


def video_status_reference(locale: str) -> dict[str, Any]:
    """返回视频任务 ``status`` 字段的取值说明与流转备注。"""

    return {
        "statuses": [
            {"status": status, "description": translate(description, locale)}
            for status, description in _STATUS_DESCRIPTIONS
        ],
        "note": translate(_STATUS_NOTE, locale),
    }


def stream_notes(stream: str | None, locale: str) -> list[str]:
    """返回该接口的流式说明。

    ``stream`` 取值与端点声明一致：``request`` 表示由请求体的 ``stream`` 字段决定，``always``
    表示接口自身始终流式；其余取值返回空列表。
    """

    if stream == "request":
        return [translate(_STREAM_NOTE, locale)]
    if stream == "always":
        return [translate(_STREAM_ALWAYS_NOTE, locale)]
    return []


def material_notes(material_fields: dict[str, Any], locale: str) -> list[str]:
    """仅当该调用形态接受素材字段时返回素材提交说明。"""

    return [translate(_MATERIAL_NOTE, locale)] if material_fields else []
