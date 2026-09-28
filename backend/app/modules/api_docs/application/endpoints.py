"""公开接口的说明声明。

键为「HTTP 方法 + 路径」，与 ``app/core/protocols/operations.py`` 输出的端点一一对应：方法、路径与
请求编码仍以协议声明为准，本模块只补充面向调用方的展示名、路径与查询参数、响应说明，避免出现
第二份端点定义。

``request_body`` 表示该接口承载调用形态的请求体参数，形态本身由模板声明给出；未在此登记的端点仍会
出现在文档里（展示名回退为路径），只是没有参数与响应说明，便于及时发现遗漏。
"""

from dataclasses import dataclass
from typing import Any

_VIDEO_ID_PARAM: dict[str, Any] = {
    "name": "video_id",
    "description": "任务 ID，取创建接口返回的 id（形如 task_<uuid>）。",
}
_GEMINI_MODEL_PARAM: dict[str, Any] = {
    "name": "model",
    "description": "模型名，取 GET /v1/models 返回的 id。",
}
_VIDEO_VARIANT_PARAM: dict[str, Any] = {
    "name": "variant",
    "description": "成品变体，当前仅支持默认值 video。",
}
_NATIVE_BODY = "响应体保持该协议原生形状，不额外包装。"


@dataclass(frozen=True)
class DocumentedEndpoint:
    """一个公开接口的说明。

    ``operation_id`` 是接口在条目内的稳定标识，供前端路由与锚点使用；``responses`` 每项含
    ``status``（HTTP 状态码）、``content_type`` 与 ``description``。
    """

    operation_id: str
    name: str
    summary: str
    request_body: bool = False
    path_params: tuple[dict[str, Any], ...] = ()
    query_params: tuple[dict[str, Any], ...] = ()
    responses: tuple[dict[str, Any], ...] = ()


ENDPOINT_DOCS: dict[tuple[str, str], DocumentedEndpoint] = {
    # 视频：创建、查询、下载三类接口
    ("POST", "/v1/videos"): DocumentedEndpoint(
        operation_id="create",
        name="创建视频任务",
        summary="提交一次生成请求并返回任务对象；异步渠道返回进行中状态，同步渠道可能在同一请求内返回成品。",
        request_body=True,
        responses=(
            {
                "status": 202,
                "content_type": "application/json",
                "description": "返回任务对象，含 id、status、progress 等字段。",
            },
        ),
    ),
    ("GET", "/v1/videos/{video_id}"): DocumentedEndpoint(
        operation_id="retrieve",
        name="获取视频任务",
        summary="按任务 ID 查询任务状态、进度、结果地址与错误信息。",
        path_params=(_VIDEO_ID_PARAM,),
        responses=(
            {
                "status": 200,
                "content_type": "application/json",
                "description": "返回任务对象，含状态、进度、结果地址与错误信息。",
            },
        ),
    ),
    ("GET", "/v1/videos/{video_id}/content"): DocumentedEndpoint(
        operation_id="download",
        name="下载视频成品",
        summary="按任务 ID 下载视频成品，返回二进制流。",
        path_params=(_VIDEO_ID_PARAM,),
        query_params=(_VIDEO_VARIANT_PARAM,),
        responses=({"status": 200, "content_type": "video/*", "description": "返回视频二进制流。"},),
    ),
    # OpenAI 兼容文本与图片
    ("POST", "/v1/chat/completions"): DocumentedEndpoint(
        operation_id="create",
        name="创建文本补全",
        summary="创建一次对话补全。",
        request_body=True,
        responses=({"status": 200, "content_type": "application/json", "description": _NATIVE_BODY},),
    ),
    ("POST", "/v1/responses"): DocumentedEndpoint(
        operation_id="create",
        name="创建响应",
        summary="创建一次 Responses 调用。",
        request_body=True,
        responses=({"status": 200, "content_type": "application/json", "description": _NATIVE_BODY},),
    ),
    ("POST", "/v1/images/generations"): DocumentedEndpoint(
        operation_id="generate",
        name="创建图片生成",
        summary="根据文本提示词生成图片。",
        request_body=True,
        responses=({"status": 200, "content_type": "application/json", "description": _NATIVE_BODY},),
    ),
    ("POST", "/v1/images/edits"): DocumentedEndpoint(
        operation_id="edit",
        name="创建图片编辑",
        summary="以 multipart 提交输入图片并生成编辑结果。",
        request_body=True,
        responses=({"status": 200, "content_type": "application/json", "description": _NATIVE_BODY},),
    ),
    # Anthropic、Gemini、千问与豆包原生协议
    ("POST", "/v1/messages"): DocumentedEndpoint(
        operation_id="create",
        name="创建 Anthropic 消息",
        summary="创建一次 Anthropic Messages 调用。",
        request_body=True,
        responses=({"status": 200, "content_type": "application/json", "description": _NATIVE_BODY},),
    ),
    ("POST", "/v1beta/models/{model}:generateContent"): DocumentedEndpoint(
        operation_id="generate",
        name="生成 Gemini 内容",
        summary="生成一次 Gemini 内容。",
        request_body=True,
        path_params=(_GEMINI_MODEL_PARAM,),
        responses=({"status": 200, "content_type": "application/json", "description": _NATIVE_BODY},),
    ),
    ("POST", "/v1beta/models/{model}:streamGenerateContent"): DocumentedEndpoint(
        operation_id="stream",
        name="流式生成 Gemini 内容",
        summary="以 SSE 增量返回 Gemini 内容。",
        request_body=True,
        path_params=(_GEMINI_MODEL_PARAM,),
        responses=({"status": 200, "content_type": "text/event-stream", "description": _NATIVE_BODY},),
    ),
    ("POST", "/api/v1/services/aigc/text-generation/generation"): DocumentedEndpoint(
        operation_id="text",
        name="创建千问文本生成",
        summary="创建一次千问文本生成。",
        request_body=True,
        responses=({"status": 200, "content_type": "application/json", "description": _NATIVE_BODY},),
    ),
    ("POST", "/api/v1/services/aigc/multimodal-generation/generation"): DocumentedEndpoint(
        operation_id="multimodal",
        name="创建千问多模态生成",
        summary="创建一次千问多模态生成。",
        request_body=True,
        responses=({"status": 200, "content_type": "application/json", "description": _NATIVE_BODY},),
    ),
    ("POST", "/api/v3/responses"): DocumentedEndpoint(
        operation_id="create",
        name="创建豆包响应",
        summary="创建一次豆包 Responses 调用。",
        request_body=True,
        responses=({"status": 200, "content_type": "application/json", "description": _NATIVE_BODY},),
    ),
}


def endpoint_doc(method: str, path: str) -> DocumentedEndpoint | None:
    """按方法与路径查找接口说明，未登记时返回空值。"""

    return ENDPOINT_DOCS.get((method, path))
