from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlmodel import Session

from app.core.auth import get_admin_user_id
from app.core.database import get_async_session_factory, get_db
from app.modules.admin.api.channels.schemas import (
    ChannelCopyRequest,
    ChannelCreateRequest,
    ChannelDeleteRequest,
    ChannelStatusUpdateRequest,
    ChannelTestRequest,
    ChannelUpdateRequest,
)
from app.modules.admin.application.model_config.channel_testing import ChannelTestApplicationService
from app.modules.admin.application.model_config.services import AdminModelConfigApplicationService

router = APIRouter(prefix="/channels", tags=["管理员视频配置"])


@router.post(
    "/create", status_code=status.HTTP_201_CREATED, dependencies=[Depends(get_admin_user_id)], summary="创建渠道"
)
def create_channel(payload: ChannelCreateRequest, session: Annotated[Session, Depends(get_db)]) -> dict[str, object]:
    return AdminModelConfigApplicationService(session).create_channel(payload.model_dump())


@router.post("/update", dependencies=[Depends(get_admin_user_id)], summary="更新渠道")
def update_channel(payload: ChannelUpdateRequest, session: Annotated[Session, Depends(get_db)]) -> dict[str, object]:
    return AdminModelConfigApplicationService(session).update_channel(payload.model_dump())


@router.post("/update-status", dependencies=[Depends(get_admin_user_id)], summary="更新渠道状态")
def update_channel_status(
    payload: ChannelStatusUpdateRequest, session: Annotated[Session, Depends(get_db)]
) -> dict[str, object]:
    return AdminModelConfigApplicationService(session).update_channel_status(payload.model_dump())


@router.post("/delete", dependencies=[Depends(get_admin_user_id)], summary="删除渠道")
def delete_channel(payload: ChannelDeleteRequest, session: Annotated[Session, Depends(get_db)]) -> dict[str, bool]:
    AdminModelConfigApplicationService(session).delete_channel(payload.model_dump())
    return {"success": True}


@router.post(
    "/copy", status_code=status.HTTP_201_CREATED, dependencies=[Depends(get_admin_user_id)], summary="复制渠道"
)
def copy_channel(payload: ChannelCopyRequest, session: Annotated[Session, Depends(get_db)]) -> dict[str, object]:
    return AdminModelConfigApplicationService(session).copy_channel(payload.model_dump())


@router.get("/list", dependencies=[Depends(get_admin_user_id)], summary="查询渠道列表")
def list_channels(
    session: Annotated[Session, Depends(get_db)],
    channel_name: Annotated[str | None, Query(max_length=128)] = None,
    model_name: Annotated[str | None, Query(max_length=128)] = None,
    token_group_name: Annotated[str | None, Query(max_length=128)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict[str, object]:
    total, items = AdminModelConfigApplicationService(session).list_channels(
        channel_name=channel_name,
        model_name=model_name,
        token_group_name=token_group_name,
        page=page,
        page_size=page_size,
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/detail", dependencies=[Depends(get_admin_user_id)], summary="查询渠道详情")
def get_channel(
    channel_id: Annotated[UUID, Query()], session: Annotated[Session, Depends(get_db)]
) -> dict[str, object]:
    return AdminModelConfigApplicationService(session).get_channel(channel_id)


@router.post("/test", summary="测试渠道上游连通性")
async def test_channel(
    payload: ChannelTestRequest, admin_user_id: Annotated[UUID, Depends(get_admin_user_id)]
) -> dict[str, object]:
    return await ChannelTestApplicationService(get_async_session_factory()).test_channel(
        admin_user_id=admin_user_id, **payload.model_dump()
    )
