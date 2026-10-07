"""Provider 无关的视频 HTTP API。

本模块负责鉴权、请求响应转换及事务边界，所有业务处理委托给视频应用服务；异步 Provider 的创建接口只提交
任务并返回进行中状态，同步 Provider 的创建接口会等待上游成品并在同一请求内返回已完成结果；鉴权下载接口
始终按字节流下发（外部直链交付时由平台反代上游），公开下载接口对这类成品重定向到上游地址。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import RedirectResponse, Response, StreamingResponse
from starlette.datastructures import UploadFile

from app.core.auth import TokenAuthorizationContext, require_token_group
from app.core.database import get_async_session_factory
from app.core.errors import ValidationError
from app.core.protocols import OPENAI_VIDEO_PROTOCOL
from app.modules.video.api.schemas import OpenAIVideoCreateRequest, OpenAIVideoId, OpenAIVideoResponse
from app.modules.video.application.tasks.async_runtime import AsyncVideoApplicationService

router = APIRouter(prefix=OPENAI_VIDEO_PROTOCOL.operation("create").path, tags=["视频"])


@router.post("", response_model=OpenAIVideoResponse, status_code=status.HTTP_202_ACCEPTED, summary="创建视频任务")
async def create_video(
    request: Request,
    token_authorization: Annotated[TokenAuthorizationContext, Depends(require_token_group)],
) -> OpenAIVideoResponse:
    if request.headers.get("content-type", "").split(";", 1)[0] == "application/json":
        try:
            raw_payload = await request.json()
        except ValueError as exc:
            raise ValidationError("请求体不是合法 JSON") from exc
        if not isinstance(raw_payload, dict):
            raise ValidationError("请求体必须是 JSON 对象")
        uploaded_files: dict[str, list[UploadFile]] = {}
    else:
        form = await request.form()
        raw_payload = {}
        uploaded_files = {}
        for key, value in form.multi_items():
            if isinstance(value, UploadFile):
                uploaded_files.setdefault(key, []).append(value)
                continue
            if key in raw_payload:
                existing = raw_payload[key]
                raw_payload[key] = existing + [value] if isinstance(existing, list) else [existing, value]
            else:
                raw_payload[key] = value
    payload = OpenAIVideoCreateRequest.model_validate(raw_payload)
    user_id = token_authorization.user_id
    group_ids = [group.id for group in token_authorization.token_groups.groups]
    video = await AsyncVideoApplicationService(get_async_session_factory()).create_openai_video(
        user_id=user_id,
        group_ids=group_ids,
        access_token_id=token_authorization.token_id,
        token_display_name=token_authorization.token_display_name,
        request=payload.model_dump(exclude_none=True),
        uploaded_files=uploaded_files,
        public_base_url=str(request.base_url),
    )
    return OpenAIVideoResponse.from_openai_data(video)


@router.get("/public/{task_id}", summary="下载公开视频成品")
async def get_public_video_content(task_id: OpenAIVideoId) -> Response:
    source = await AsyncVideoApplicationService(get_async_session_factory()).get_public_video_content(task_id=task_id)
    if source.redirect_url is not None:
        return RedirectResponse(source.redirect_url, status_code=status.HTTP_302_FOUND)
    return StreamingResponse(
        source.chunks,
        media_type=source.content_type,
        headers={"Content-Disposition": f'inline; filename="video-{task_id}.mp4"'},
    )


@router.get("/materials/{resource_id}", summary="下载视频输入素材")
async def get_material_content(resource_id: str) -> Response:
    chunks, content_type = await AsyncVideoApplicationService(get_async_session_factory()).get_material_content(
        resource_id=resource_id
    )
    return StreamingResponse(chunks, media_type=content_type)


@router.get("/{video_id}", response_model=OpenAIVideoResponse, summary="获取视频任务")
async def get_video(
    request: Request,
    video_id: OpenAIVideoId,
    token_authorization: Annotated[TokenAuthorizationContext, Depends(require_token_group)],
) -> OpenAIVideoResponse:
    video = await AsyncVideoApplicationService(get_async_session_factory()).get_owned_openai_video(
        video_id=video_id, user_id=token_authorization.user_id, public_base_url=str(request.base_url)
    )
    return OpenAIVideoResponse.from_openai_data(video)


@router.get("/{video_id}/content", summary="下载视频成品")
async def get_video_content(
    video_id: OpenAIVideoId,
    token_authorization: Annotated[TokenAuthorizationContext, Depends(require_token_group)],
    variant: str = "video",
) -> Response:
    source = await AsyncVideoApplicationService(get_async_session_factory()).get_owned_video_content(
        video_id=video_id, user_id=token_authorization.user_id, variant=variant
    )
    return StreamingResponse(source.chunks, media_type=source.content_type)
