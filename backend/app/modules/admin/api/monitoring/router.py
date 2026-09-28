"""管理员分组监控 HTTP 接口。"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends
from sqlmodel import Session

from app.core.auth import get_admin_user_id
from app.core.database import get_db
from app.modules.admin.api.monitoring.schemas import (
    AdminAlertListQuery,
    AdminAlertRuleDeleteRequest,
    AdminAlertRuleUpdateRequest,
    AdminAlertStatusUpdateRequest,
    AdminChannelMonitorQuery,
    AdminGroupMonitorListQuery,
    AdminGroupMonitorTrendQuery,
    AdminNotificationUpdateRequest,
    AdminResourceRuleUpdateRequest,
    AdminServerMetricTrendQuery,
    AlertScopeValue,
)
from app.modules.monitoring.application.alerting import MonitorAlertApplicationService
from app.modules.monitoring.application.query_services import GroupMonitorQueryApplicationService
from app.modules.monitoring.application.resource_settings import MonitorResourceSettingsApplicationService
from app.modules.monitoring.application.server_query_services import ServerMetricQueryApplicationService
from app.modules.monitoring.application.settings import MonitorSettingsApplicationService
from app.modules.monitoring.model import MonitorAlertStatus

router = APIRouter(prefix="/monitoring", tags=["管理员分组监控"])

SERVER_TAGS = ["管理员服务器监控"]
"""服务器资源监控接口的 OpenAPI 标签，便于前端按运维/业务分栏渲染。"""


@router.get("/groups/list", summary="查询全部分组监控指标")
def list_group_metrics(
    payload: Annotated[AdminGroupMonitorListQuery, Depends()],
    _: Annotated[UUID, Depends(get_admin_user_id)],
    session: Annotated[Session, Depends(get_db)],
) -> dict:
    return GroupMonitorQueryApplicationService(session).admin_group_metrics(group_id=payload.group_id)


@router.get("/groups/trend", summary="查询指定分组监控指标趋势")
def group_metrics_trend(
    payload: Annotated[AdminGroupMonitorTrendQuery, Depends()],
    _: Annotated[UUID, Depends(get_admin_user_id)],
    session: Annotated[Session, Depends(get_db)],
) -> dict:
    return GroupMonitorQueryApplicationService(session).group_trend(
        group_id=payload.group_id,
        request_type=payload.request_type,
        hours=payload.hours,
    )


@router.get("/channels/list", summary="查询渠道维度监控指标")
def list_channel_metrics(
    payload: Annotated[AdminChannelMonitorQuery, Depends()],
    _: Annotated[UUID, Depends(get_admin_user_id)],
    session: Annotated[Session, Depends(get_db)],
) -> dict:
    return GroupMonitorQueryApplicationService(session).channel_metrics(group_id=payload.group_id)


@router.get("/alerts/list", summary="分页查询分组监控告警")
def list_alerts(
    payload: Annotated[AdminAlertListQuery, Depends()],
    _: Annotated[UUID, Depends(get_admin_user_id)],
    session: Annotated[Session, Depends(get_db)],
) -> dict:
    return GroupMonitorQueryApplicationService(session).alert_list(
        status=payload.status,
        group_id=payload.group_id,
        channel_id=payload.channel_id,
        metric=payload.metric,
        scope=payload.scope,
        hours=payload.hours,
        page=payload.page,
        page_size=payload.page_size,
    )


@router.post("/alerts/update-status", summary="处置分组监控告警")
def update_alert_status(
    payload: AdminAlertStatusUpdateRequest,
    _: Annotated[UUID, Depends(get_admin_user_id)],
    session: Annotated[Session, Depends(get_db)],
) -> dict:
    return MonitorAlertApplicationService(session).mark_status(
        alert_id=payload.alert_id, status=MonitorAlertStatus(payload.status)
    )


@router.get("/alert-rules/list", summary="查询分组监控告警规则")
def list_alert_rules(
    _: Annotated[UUID, Depends(get_admin_user_id)],
    session: Annotated[Session, Depends(get_db)],
) -> dict:
    return {"items": MonitorSettingsApplicationService(session).list_rule_views()}


@router.post("/alert-rules/update", summary="新增或更新分组监控告警规则")
def update_alert_rule(
    payload: AdminAlertRuleUpdateRequest,
    _: Annotated[UUID, Depends(get_admin_user_id)],
    session: Annotated[Session, Depends(get_db)],
) -> dict:
    return MonitorSettingsApplicationService(session).upsert_rule(payload.model_dump(exclude_unset=True))


@router.post("/alert-rules/delete", summary="删除分组监控告警规则")
def delete_alert_rule(
    payload: AdminAlertRuleDeleteRequest,
    _: Annotated[UUID, Depends(get_admin_user_id)],
    session: Annotated[Session, Depends(get_db)],
) -> dict:
    MonitorSettingsApplicationService(session).delete_group_rule(payload.group_id)
    return {"success": True}


@router.get("/notification/detail", summary="查询分组监控推送配置")
def get_notification(
    _: Annotated[UUID, Depends(get_admin_user_id)],
    session: Annotated[Session, Depends(get_db)],
) -> dict:
    return MonitorSettingsApplicationService(session).notification_view()


@router.post("/notification/update", summary="更新分组监控推送配置")
def update_notification(
    payload: AdminNotificationUpdateRequest,
    _: Annotated[UUID, Depends(get_admin_user_id)],
    session: Annotated[Session, Depends(get_db)],
) -> dict:
    return MonitorSettingsApplicationService(session).update_notification(payload.model_dump(exclude_unset=True))


@router.post("/notification/test", summary="发送监控推送测试通知")
def send_test_notification(
    _: Annotated[UUID, Depends(get_admin_user_id)],
    session: Annotated[Session, Depends(get_db)],
    scope: Annotated[
        AlertScopeValue,
        Body(
            embed=True,
            description="告警范围：group 为分组业务告警，server 为服务器资源告警；不传或传 null 按 group 处理",
        ),
    ] = "group",
) -> dict:
    return MonitorSettingsApplicationService(session).send_test_notification(scope)


@router.get("/server/latest", summary="查询服务器资源最新指标", tags=SERVER_TAGS)
def get_server_metrics_latest(
    _: Annotated[UUID, Depends(get_admin_user_id)],
    session: Annotated[Session, Depends(get_db)],
) -> dict:
    return ServerMetricQueryApplicationService(session).latest()


@router.get("/server/trend", summary="查询服务器资源指标趋势", tags=SERVER_TAGS)
def get_server_metrics_trend(
    payload: Annotated[AdminServerMetricTrendQuery, Depends()],
    _: Annotated[UUID, Depends(get_admin_user_id)],
    session: Annotated[Session, Depends(get_db)],
) -> dict:
    return ServerMetricQueryApplicationService(session).trend(hours=payload.hours)


@router.get("/resource-rules/detail", summary="查询服务器资源告警阈值", tags=SERVER_TAGS)
def get_resource_rules(
    _: Annotated[UUID, Depends(get_admin_user_id)],
    session: Annotated[Session, Depends(get_db)],
) -> dict:
    return MonitorResourceSettingsApplicationService(session).rule_view()


@router.post("/resource-rules/update", summary="更新服务器资源告警阈值", tags=SERVER_TAGS)
def update_resource_rules(
    payload: AdminResourceRuleUpdateRequest,
    _: Annotated[UUID, Depends(get_admin_user_id)],
    session: Annotated[Session, Depends(get_db)],
) -> dict:
    return MonitorResourceSettingsApplicationService(session).update_rule(payload.model_dump(exclude_unset=True))
