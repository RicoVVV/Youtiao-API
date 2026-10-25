"""OpenAI 兼容的图片与文本同步生成 HTTP 接口。

本模块负责鉴权、请求体解析与响应转发，业务处理全部委托给同步生成应用服务；图片与文本结果均按
上游响应原样透传，不在 HTTP 层解释或改写字段。
"""

import json
import os
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse, Response, StreamingResponse
from starlette.datastructures import UploadFile

from app.core.auth import TokenAuthorizationContext, require_token_group
from app.core.database import get_async_session_factory
from app.core.errors import ValidationError
from app.core.protocols import (
    ANTHROPIC_MESSAGES_PROTOCOL,
    ARK_RESPONSES_PROTOCOL,
    DASHSCOPE_MULTIMODAL_PROTOCOL,
    DASHSCOPE_TEXT_PROTOCOL,
    GEMINI_TEXT_PROTOCOL,
    OPENAI_IMAGE_PROTOCOL,
    OPENAI_MODELS_PROTOCOL,
    OPENAI_RESPONSE_PROTOCOL,
    OPENAI_TEXT_PROTOCOL,
)
from app.modules.generation.application.services import (
    GeminiContentApplicationService,
    ImageGenerationApplicationService,
    ModelCatalogApplicationService,
    TextGenerationApplicationService,
)
from app.modules.providers.anthropic.adapter import (
    CHAT_COMPLETIONS_ENDPOINT,
    MESSAGES_ENDPOINT,
)
from app.modules.providers.anthropic.adapter import (
    ENDPOINT_FIELD as ANTHROPIC_ENDPOINT_FIELD,
)
from app.modules.providers.contracts import ProviderUpload
from app.modules.providers.dashscope.adapter import (
    ENDPOINT_FIELD,
    MULTIMODAL_ENDPOINT,
)
from app.web.request_body import read_json_body
from app.web.streaming import streaming_response

router = APIRouter(tags=["生成"])

# 图片编辑输入文件上限与业务规则一致：单文件 25 MB（上游 GPT Image 单图限制）、最多 16 个。
# 网关的 client_max_body_size 必须不低于该总量，否则多张 4K 图片会在 nginx 层被拦。
_MAX_UPLOAD_FILE_BYTES = 25 * 1024 * 1024
_MAX_UPLOAD_FILES = 16
_MAX_UPLOAD_TOTAL_BYTES = _MAX_UPLOAD_FILES * _MAX_UPLOAD_FILE_BYTES


@router.post(OPENAI_IMAGE_PROTOCOL.operation("create").path, summary="创建图片生成")
async def create_image(
    request: Request,
    token_authorization: Annotated[TokenAuthorizationContext, Depends(require_token_group)],
) -> JSONResponse:
    payload = await _read_json_request(request)
    result = await ImageGenerationApplicationService(get_async_session_factory()).generate_image(
        **_authorization_kwargs(token_authorization), payload=payload
    )
    return JSONResponse(content=result)


@router.post(OPENAI_IMAGE_PROTOCOL.operation("edit").path, summary="创建图片编辑")
async def create_image_edit(
    request: Request,
    token_authorization: Annotated[TokenAuthorizationContext, Depends(require_token_group)],
) -> JSONResponse:
    payload, uploads = await _read_multipart_request(request)
    result = await ImageGenerationApplicationService(get_async_session_factory()).edit_image(
        **_authorization_kwargs(token_authorization), payload=payload, uploads=uploads
    )
    return JSONResponse(content=result)


@router.post(OPENAI_TEXT_PROTOCOL.operation("create").path, summary="创建文本补全")
async def create_chat_completion(
    request: Request,
    token_authorization: Annotated[TokenAuthorizationContext, Depends(require_token_group)],
) -> Response:
    payload = await _read_json_request(request)
    # 公开路径决定调用形状：Anthropic 模型经该路径按 OpenAI Chat Completions 形状调用。
    payload[ANTHROPIC_ENDPOINT_FIELD] = CHAT_COMPLETIONS_ENDPOINT
    service = TextGenerationApplicationService(get_async_session_factory())
    if payload.get("stream") is True:
        stream, content_type = await service.chat_stream(**_authorization_kwargs(token_authorization), payload=payload)
        return streaming_response(request, stream, content_type)
    result = await service.chat(**_authorization_kwargs(token_authorization), payload=payload)
    return JSONResponse(content=result)


@router.post(OPENAI_RESPONSE_PROTOCOL.operation("create").path, summary="创建响应")
async def create_response(
    request: Request,
    token_authorization: Annotated[TokenAuthorizationContext, Depends(require_token_group)],
) -> Response:
    payload = await _read_json_request(request)
    service = TextGenerationApplicationService(get_async_session_factory())
    if payload.get("stream") is True:
        stream, content_type = await service.response_stream(
            **_authorization_kwargs(token_authorization), payload=payload
        )
        return streaming_response(request, stream, content_type)
    result = await service.create_response(**_authorization_kwargs(token_authorization), payload=payload)
    return JSONResponse(content=result)


@router.post(GEMINI_TEXT_PROTOCOL.operation("generate").path, summary="生成 Gemini 内容")
async def generate_gemini_content(
    model: str,
    request: Request,
    token_authorization: Annotated[TokenAuthorizationContext, Depends(require_token_group)],
) -> JSONResponse:
    payload = await _read_json_request(request)
    payload["model"] = model
    result = await TextGenerationApplicationService(get_async_session_factory()).chat(
        **_authorization_kwargs(token_authorization), payload=payload
    )
    return JSONResponse(content=result)


@router.post(GEMINI_TEXT_PROTOCOL.operation("stream").path, summary="流式生成 Gemini 内容")
async def stream_gemini_content(
    model: str,
    request: Request,
    token_authorization: Annotated[TokenAuthorizationContext, Depends(require_token_group)],
) -> StreamingResponse:
    payload = await _read_json_request(request)
    payload["model"] = model
    stream, content_type = await GeminiContentApplicationService(get_async_session_factory()).stream_generate_content(
        **_authorization_kwargs(token_authorization), payload=payload
    )
    return streaming_response(request, stream, content_type)


@router.post(
    DASHSCOPE_TEXT_PROTOCOL.operation("create").path,
    summary="创建千问文本生成",
)
async def create_dashscope_text(
    request: Request,
    token_authorization: Annotated[TokenAuthorizationContext, Depends(require_token_group)],
) -> Response:
    payload = await _read_json_request(request)
    return await _dashscope_generation(request, token_authorization, payload)


@router.post(
    DASHSCOPE_MULTIMODAL_PROTOCOL.operation("create").path,
    summary="创建千问多模态生成",
)
async def create_dashscope_multimodal(
    request: Request,
    token_authorization: Annotated[TokenAuthorizationContext, Depends(require_token_group)],
) -> Response:
    payload = await _read_json_request(request)
    payload[ENDPOINT_FIELD] = MULTIMODAL_ENDPOINT
    return await _dashscope_generation(request, token_authorization, payload)


@router.post(ANTHROPIC_MESSAGES_PROTOCOL.operation("create").path, summary="创建 Anthropic 消息")
async def create_anthropic_message(
    request: Request,
    token_authorization: Annotated[TokenAuthorizationContext, Depends(require_token_group)],
) -> Response:
    payload = await _read_json_request(request)
    # 公开路径决定调用形状：Anthropic 原生 Messages 请求体原样转发。
    payload[ANTHROPIC_ENDPOINT_FIELD] = MESSAGES_ENDPOINT
    service = TextGenerationApplicationService(get_async_session_factory())
    if payload.get("stream") is True:
        stream, content_type = await service.chat_stream_native(
            **_authorization_kwargs(token_authorization), payload=payload
        )
        return streaming_response(request, stream, content_type)
    result = await service.chat(**_authorization_kwargs(token_authorization), payload=payload)
    return JSONResponse(content=result)


@router.post(ARK_RESPONSES_PROTOCOL.operation("create").path, summary="创建豆包响应")
async def create_ark_response(
    request: Request,
    token_authorization: Annotated[TokenAuthorizationContext, Depends(require_token_group)],
) -> Response:
    payload = await _read_json_request(request)
    service = TextGenerationApplicationService(get_async_session_factory())
    if payload.get("stream") is True:
        stream, content_type = await service.response_stream(
            **_authorization_kwargs(token_authorization), payload=payload
        )
        return streaming_response(request, stream, content_type)
    result = await service.create_response(**_authorization_kwargs(token_authorization), payload=payload)
    return JSONResponse(content=result)


async def _dashscope_generation(
    request: Request,
    token_authorization: TokenAuthorizationContext,
    payload: dict[str, Any],
) -> Response:
    """按 DashScope 原生约定分流同步 JSON 与 SSE 增量输出。"""

    service = TextGenerationApplicationService(get_async_session_factory())
    if _wants_sse(request):
        stream, content_type = await service.chat_stream_native(
            **_authorization_kwargs(token_authorization), payload=payload
        )
        return streaming_response(request, stream, content_type)
    result = await service.chat(**_authorization_kwargs(token_authorization), payload=payload)
    return JSONResponse(content=result)


def _wants_sse(request: Request) -> bool:
    """DashScope 通过请求头开关 SSE，二者任一命中即按流式输出。"""

    if request.headers.get("x-dashscope-sse", "").strip().lower() == "enable":
        return True
    return "text/event-stream" in request.headers.get("accept", "").lower()


@router.get(OPENAI_MODELS_PROTOCOL.operation("list").path, summary="查询可用模型列表")
async def list_models(
    token_authorization: Annotated[TokenAuthorizationContext, Depends(require_token_group)],
) -> JSONResponse:
    result = await ModelCatalogApplicationService(get_async_session_factory()).list_models(
        group_ids=[group.id for group in token_authorization.token_groups.groups]
    )
    return JSONResponse(content=result)


@router.get(GEMINI_TEXT_PROTOCOL.operation("list").path, summary="查询 Gemini 可用模型列表")
async def list_gemini_models(
    token_authorization: Annotated[TokenAuthorizationContext, Depends(require_token_group)],
) -> JSONResponse:
    result = await ModelCatalogApplicationService(get_async_session_factory()).list_gemini_models(
        group_ids=[group.id for group in token_authorization.token_groups.groups]
    )
    return JSONResponse(content=result)


def _authorization_kwargs(token_authorization: TokenAuthorizationContext) -> dict[str, Any]:
    """把已鉴权上下文转换为应用服务所需的调用参数。"""

    return {
        "user_id": token_authorization.user_id,
        "group_ids": [group.id for group in token_authorization.token_groups.groups],
        "access_token_id": token_authorization.token_id,
        "token_display_name": token_authorization.token_display_name,
    }


async def _read_json_request(request: Request) -> dict[str, Any]:
    """读取 JSON 请求体并保证顶层为对象；读取过程带上限，超限在解析前返回 413。"""

    raw = await read_json_body(request)
    try:
        payload = json.loads(raw)
    except ValueError as exc:
        raise ValidationError("请求体不是合法 JSON") from exc
    if not isinstance(payload, dict):
        raise ValidationError("请求体必须是 JSON 对象")
    return payload


async def _read_multipart_request(request: Request) -> tuple[dict[str, Any], list[ProviderUpload]]:
    """解析 multipart 请求，分离普通字段与待转发文件。

    文件不读入内存，只按解析阶段得到的字节数校验上限，随后把文件对象交给上游适配器流式转发。
    """

    content_length = request.headers.get("content-length")
    if content_length and content_length.isdigit() and int(content_length) > _MAX_UPLOAD_TOTAL_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="请求体超出大小限制")
    form = await request.form()
    payload: dict[str, Any] = {}
    uploads: list[ProviderUpload] = []
    upload_bytes = 0
    for key, value in form.multi_items():
        if isinstance(value, UploadFile):
            size = _upload_size(value)
            if size > _MAX_UPLOAD_FILE_BYTES or upload_bytes + size > _MAX_UPLOAD_TOTAL_BYTES:
                raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="请求体超出大小限制")
            upload_bytes += size
            uploads.append(
                ProviderUpload(
                    field_name=key,
                    filename=value.filename or key,
                    stream=value.file,
                    size=size,
                    content_type=value.content_type or "application/octet-stream",
                )
            )
            continue
        existing = payload.get(key)
        if existing is None:
            payload[key] = value
        elif isinstance(existing, list):
            existing.append(value)
        else:
            payload[key] = [existing, value]
    return payload, uploads


def _upload_size(upload: UploadFile) -> int:
    """返回上传文件字节数：优先用 Starlette 解析时累计的 size，缺失时按文件对象计算。"""

    if upload.size is not None:
        return upload.size
    upload.file.seek(0, os.SEEK_END)
    size = upload.file.tell()
    upload.file.seek(0)
    return size
