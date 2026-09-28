"""视频应用服务。

本模块编排视频任务创建、报价预占、归属查询、媒体安全访问和状态事件持久化；它不直接调用上游
Provider，异步提交、轮询和下载由 Worker 完成，调用者负责提交或回滚数据库事务。
"""

import json
import logging
import re
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlmodel import Session

from app.bootstrap.container import get_channel_provider_factory, get_provider_template_registry
from app.core.errors import NotFoundError, ValidationError, error_context
from app.modules.channels.application.concurrency import release_task_concurrency, reserve_task_concurrency
from app.modules.channels.application.configuration import resolve_video_model
from app.modules.channels.application.model_mapping import apply_upstream_model_name
from app.modules.channels.application.routing import select_channel_in_group_order
from app.modules.channels.crud.channels import ChannelCrud
from app.modules.channels.model.channel import Channel
from app.modules.channels.runtime.routing_snapshot import list_routable_channel_bindings
from app.modules.models.model import ModelRoute
from app.modules.pricing.application.engine import (
    MaterialFacts,
    chargeable_material_tokens,
    list_unpriced_groups,
    missing_pricing_rule_message,
    quote_pricing,
)
from app.modules.providers.contracts import CreateVideoCommand, ProviderError
from app.modules.usage.application.services import UsageApplicationService
from app.modules.user.crud.token_group_crud import TokenGroupCrud
from app.modules.video.application.contracts import OpenAIVideoData, VideoTaskData
from app.modules.video.application.tasks.lifecycle import ensure_transition
from app.modules.video.crud.materials.input_materials import InputMaterialCrud
from app.modules.video.crud.tasks.sync import VideoTaskCrud
from app.modules.video.model.input_material import VideoInputMaterial
from app.modules.video.model.video_task import (
    RESULT_DELIVERY_EXTERNAL,
    RESULT_DELIVERY_KEY,
    TaskEvent,
    VideoTask,
    VideoTaskStatus,
)

logger = logging.getLogger(__name__)

_TERMINAL_TASK_STATUSES = {
    VideoTaskStatus.succeeded,
    VideoTaskStatus.failed,
    VideoTaskStatus.cancelled,
    VideoTaskStatus.timed_out,
}
_PUBLIC_ERROR_CODE_PATTERN = re.compile(r"^(?:[a-z0-9_]{1,64}|[1-5]\d{2})$")
_ERROR_MESSAGE_MAX_LENGTH = 500
_SENSITIVE_ERROR_MESSAGE_PATTERN = re.compile(
    r"(?:api[_-]?key|access[_-]?token|token|authorization|password|secret|signature)\s*(?:=|:|bearer\s+)\s*\S+",
    re.IGNORECASE,
)
_INTERNAL_ERROR_MESSAGE_PATTERN = re.compile(
    r"(?:[A-Za-z]:[\\/]|/(?:app|home|tmp|var|usr)/|traceback|stack trace)",
    re.IGNORECASE,
)
_TIMEOUTABLE_TASK_STATUSES = {
    VideoTaskStatus.submission_unknown,
    VideoTaskStatus.queued,
    VideoTaskStatus.processing,
}


def _create_video_task(
    session: Session,
    *,
    user_id: UUID,
    group_ids: list[int],
    access_token_id: UUID,
    token_display_name: str | None,
    request: dict,
    material_facts: MaterialFacts | None = None,
    input_materials: tuple | None = None,
) -> VideoTask:
    """创建已报价预占并待同步提交的视频任务。

    参数包括数据库会话、任务所有者、由适配层传入的请求字典及渠道编码。新任务依次冻结模型配置、创建报价、
    预占钱包金额并写入 ``submitting`` 审计事件。价格规则或钱包缺失时
    抛出 ``ValueError``，余额不足异常由钱包服务透传；本函数不提交事务。
    """

    task_crud = VideoTaskCrud(session)
    payload = dict(request)
    material_facts = material_facts or MaterialFacts()
    resolved = resolve_video_model(session, payload)
    normalized = resolved.normalized_request
    routed = _resolve_new_configuration(
        session,
        resolved.model_config,
        normalized,
        group_ids=group_ids,
        material_facts=material_facts,
    )
    task = VideoTask(
        created_at=datetime.now(UTC),
        user_id=user_id,
        model_id=resolved.model_config.id,
        token_group_id=routed.binding.token_group_id,
        status=VideoTaskStatus.submitting,
        input_payload=payload,
        normalized_input=dict(normalized.standardized_fields),
        prompt=normalized.standardized_fields.get("prompt"),
        duration_seconds=normalized.duration_seconds,
        execution_snapshot=routed.execution_snapshot,
        pricing_snapshot=routed.decision.snapshot,
    )
    task_crud.create(task)
    if input_materials:
        InputMaterialCrud(session).create_many(
            VideoInputMaterial(
                task_id=task.id,
                field_name=material.field_name,
                position=material.position,
                category=material.category,
                resource_id=material.resource_id,
                content_sha256=material.content_sha256,
                size_bytes=material.size_bytes,
                duration_seconds=material.duration_seconds,
                extras=material.extras,
            )
            for material in input_materials
        )
    estimated_amount = routed.decision.amount
    reserve_task_concurrency(session, task_id=task.id, user_id=user_id, model_id=task.model_id)
    UsageApplicationService(session).create_reserved(
        user_id=user_id,
        access_token_id=access_token_id,
        token_display_name=token_display_name,
        token_group_id=routed.binding.token_group_id,
        request_id=str(task.id),
        request_type="video",
        resource_type="video_task",
        resource_id=task.id,
        model_id=resolved.model_config.id,
        model_name=resolved.model_name,
        channel_id=routed.channel.id,
        channel_name=routed.channel.name,
        provider_name=routed.provider_name,
        request_payload=payload,
        amount=estimated_amount,
        reason="视频生成调用扣费",
    )
    logger.info(
        "视频任务扣费已编排待事务提交 task_id=%s user_id=%s amount=%s",
        task.id,
        user_id,
        estimated_amount,
    )
    VideoTaskCrud(session).add_event(
        TaskEvent(
            task_id=task.id,
            from_status=None,
            to_status=task.status.value,
            event_type="task_created",
            payload=_billing_context(normalized, routed),
        )
    )
    return task


class _RoutedConfiguration:
    """封装新模型创建链路中必须共同冻结的渠道、映射和报价决策。"""

    def __init__(
        self,
        binding: ModelRoute,
        channel: Channel,
        provider_name: str,
        execution_snapshot: dict,
        provider_request: dict,
        decision,
    ) -> None:
        """保存已选渠道、模型协议及其脱敏快照，供任务、报价和资金上下文复用。"""

        self.binding = binding
        self.channel = channel
        self.provider_name = provider_name
        self.execution_snapshot = execution_snapshot
        self.provider_request = provider_request
        self.decision = decision


def _resolve_new_configuration(
    session: Session, public_model, normalized, *, group_ids: list[int], material_facts: MaterialFacts | None = None
) -> _RoutedConfiguration:
    """读取当前公开模型的渠道、规则和时区，并生成一次创建请求的完整冻结决策。

    参数为事务会话、已解析的公开模型版本及标准化请求。主分组优先，主分组缺少可用渠道或匹配计费方案时
    按绑定顺序尝试兜底分组；全部候选分组都不可用时抛出 ``ValueError``，调用方在任何资金写入前回滚。
    候选分组没有启用定价规则时，报错明确指向缺失定价规则的分组。
    """

    material_facts = material_facts or MaterialFacts()
    source = normalized.provider_request
    channel_crud = ChannelCrud(session)
    channels = list_routable_channel_bindings(
        session,
        model_id=public_model.id,
        group_ids=group_ids,
        loader=lambda: channel_crud.list_channels_for_model(model_id=public_model.id, group_ids=group_ids),
    )
    fetched_rules: list | None = None
    created_at = datetime.now(UTC)
    attempted = False
    unmatched_group_ids: list[int] = []
    for route in select_channel_in_group_order(channels, group_ids=group_ids):
        attempted = True
        template = get_provider_template_registry().get_internal(public_model.template_id)
        if template is None:
            raise ValueError("模型模板不存在")
        provider_type = template["provider_type"]
        provider_request = dict(source)
        selected_snapshot = _selected_channel_snapshot(route)
        if provider_type == "fal":
            provider_config = template["provider_config"]
        else:
            apply_upstream_model_name(provider_request, route.channel.model_mapping.get(public_model.name))
            provider_request.update(route.channel.param_override)
            provider_config = dict(selected_snapshot["config"])
        try:
            provider = get_channel_provider_factory().get_frozen_provider(
                {**selected_snapshot, "config": provider_config},
                provider_type=provider_type,
                api_key=route.channel.api_key,
            )
            provider.validate_request(provider_request)
        except ProviderError as exc:
            # 沿用渠道 Provider 的具体校验文案，使 422 响应直接指出被拒字段，而不是统一为“契约不合法”。
            raise ValueError(str(exc)) from exc
        rules, items, modifiers = channel_crud.list_pricing_configuration(model_id=public_model.id)
        fetched_rules = rules
        items_by_rule = defaultdict(list)
        for item in items:
            items_by_rule[item.pricing_rule_id].append(item)
        modifiers_by_rule = defaultdict(list)
        for modifier in modifiers:
            modifiers_by_rule[modifier.pricing_rule_id].append(modifier)
        context = dict(source)
        # 未声明投影的标准字段保持空值，不能覆盖同名公开字段，否则按公开字段配置的计费规则会全部失配。
        context.update({field: value for field, value in normalized.standardized_fields.items() if value is not None})
        if normalized.normalized_resolution is not None:
            context["normalized_resolution"] = normalized.normalized_resolution
        if normalized.duration_seconds is not None:
            context["seconds"] = normalized.duration_seconds
        if normalized.workflow_id is not None:
            context["workflow_id"] = normalized.workflow_id
        selected_group = TokenGroupCrud(session).get_group(route.binding.token_group_id)
        group_multiplier = selected_group.price_multiplier if selected_group is not None else Decimal("1.000000")
        try:
            decision = quote_pricing(
                rules,
                items_by_rule,
                modifiers_by_rule,
                context=context,
                facts=material_facts,
                allowed_fields=public_model.pricing_fields,
                group_ids=[route.binding.token_group_id],
                created_at=created_at,
                group_multipliers={route.binding.token_group_id: group_multiplier},
            )
        except ValueError:
            unmatched_group_ids.append(route.binding.token_group_id)
            continue
        execution_snapshot = {
            "provider_type": provider_type,
            "route": {"id": str(route.binding.id), "token_group_id": route.binding.token_group_id},
            "channel": selected_snapshot,
            "provider_request": provider_request,
            RESULT_DELIVERY_KEY: RESULT_DELIVERY_EXTERNAL if provider.delivers_external_result else "local",
        }
        if provider_type == "fal":
            execution_snapshot["provider_config"] = provider_config
        return _RoutedConfiguration(
            route.binding, route.channel, provider_type, execution_snapshot, provider_request, decision
        )
    if not attempted:
        raise ValueError("当前模型没有可用渠道")
    unpriced_group_ids = list_unpriced_groups(fetched_rules or [], group_ids=unmatched_group_ids)
    if unpriced_group_ids:
        raise ValueError(missing_pricing_rule_message(model_name=public_model.name, group_ids=unpriced_group_ids))
    raise ValueError("主分组与兜底分组均没有可匹配的计费方案")


def _selected_channel_snapshot(route) -> dict:
    """复制已选渠道冻结字段，避免后续配置对象变更影响正在创建的任务。"""

    return next(candidate for candidate in route.candidates if candidate["route_id"] == str(route.binding.id))


def _get_frozen_channel_provider(session: Session, *, task: VideoTask):
    """按任务冻结的渠道配置和当前凭证构造 Provider。"""

    execution_snapshot = task.execution_snapshot
    if not execution_snapshot:
        raise ProviderError("冻结渠道引用不完整", code="unknown_provider", retryable=False)
    channel_crud = ChannelCrud(session)
    selected = execution_snapshot.get("channel")
    if not isinstance(selected, dict) or not isinstance(selected.get("channel_id"), str):
        raise ProviderError("冻结渠道快照不合法", code="unknown_provider", retryable=False)
    try:
        channel_id = UUID(selected["channel_id"])
    except ValueError as exc:
        raise ProviderError("冻结渠道快照不合法", code="unknown_provider", retryable=False) from exc
    channel = channel_crud.get_channel_by_id(channel_id=channel_id)
    if channel is None:
        raise ProviderError("冻结渠道配置不可用", code="unknown_provider", retryable=False)
    provider_type = execution_snapshot.get("provider_type")
    if not isinstance(provider_type, str) or not provider_type:
        raise ProviderError("冻结模型协议不可用", code="unknown_provider", retryable=False)
    provider_config = execution_snapshot.get("provider_config", selected.get("config", {}))
    if not isinstance(provider_config, dict):
        raise ProviderError("冻结 Provider 配置不可用", code="unknown_provider", retryable=False)
    return get_channel_provider_factory().get_frozen_provider(
        {**selected, "config": provider_config}, provider_type=provider_type, api_key=channel.api_key
    )


def _billing_context(normalized, routed: _RoutedConfiguration) -> dict:
    """构造钱包、扣费单和任务事件共用的脱敏冻结上下文。"""
    return {
        "workflow_id": normalized.workflow_id,
        "execution": routed.execution_snapshot,
        "pricing": routed.decision.snapshot,
    }


def _get_owned_video_task(session: Session, *, task_id: UUID, user_id: UUID) -> VideoTask | None:
    """按用户归属读取视频任务。

    参数为当前会话、任务 ID 和调用用户 ID；返回属于该用户的任务，未找到或归属不符时返回 ``None``，
    不写入数据库，以避免跨租户泄露任务状态。
    """

    return VideoTaskCrud(session).get_owned(task_id=task_id, user_id=user_id)


def _list_video_tasks(session: Session, *, user_id: UUID) -> list[VideoTask]:
    """读取当前用户的视频任务投影数据。

    参数为数据库会话和鉴权用户标识；仅返回该用户所属任务，不修改数据库，供 API 层构造响应。
    """

    return VideoTaskCrud(session).list_by_user(user_id=user_id)


def _transition_task(
    session: Session, *, task: VideoTask, target: VideoTaskStatus, event_type: str, payload: dict | None = None
) -> None:
    """校验后更新任务状态并追加审计事件。

    参数为当前会话、待更新任务、目标状态、业务事件类型及可选脱敏载荷；非法状态转移抛出
    ``InvalidVideoTaskTransition``。终态会写入完成时间供调度排除，本函数不提交事务。
    """

    ensure_transition(task.status, target)
    source = task.status
    task.status = target
    # 完成时间仅在首次进入终态时设置，状态机禁止终态再迁移以保护该审计时间。
    if target in {
        VideoTaskStatus.succeeded,
        VideoTaskStatus.failed,
        VideoTaskStatus.cancelled,
        VideoTaskStatus.timed_out,
    }:
        task.completed_at = datetime.now(UTC)
    VideoTaskCrud(session).add_event(
        TaskEvent(
            task_id=task.id,
            from_status=source.value,
            to_status=target.value,
            event_type=event_type,
            payload=payload or {},
        )
    )
    logger.info(
        "视频任务状态已更新 task_id=%s from_status=%s to_status=%s event_type=%s",
        task.id,
        source.value,
        target.value,
        event_type,
    )


def _terminate_task_and_release_charge(
    session: Session,
    *,
    task: VideoTask,
    target: VideoTaskStatus,
    event_type: str,
    error_code: str,
    error_message: str,
    upstream_response_payload: dict | None = None,
) -> bool:
    """将尚未终态的视频任务终止，并在同一事务中幂等释放其预占资金。

    参数：
        task: 当前仍处于可执行状态的视频任务。
        target: 仅允许传入 ``failed``、``cancelled`` 或 ``timed_out`` 的终态。
        event_type: 用于审计此次终止来源的稳定事件编码。
        error_code/error_message: 可安全持久化的结构化错误摘要。
        upstream_response_payload: 可安全持久化的上游错误响应，用于在使用记录中还原失败原因。

    异常/副作用：
        非法目标状态会触发状态机异常；取得裁决权时更新任务错误快照、追加事件并释放预占。
        若任务已终态、目标为超时但任务不在可超时执行态，或扣费单已非预占态则返回 ``False``；调用方
        必须提交或回滚整个事务。
    """

    if target not in {VideoTaskStatus.failed, VideoTaskStatus.cancelled, VideoTaskStatus.timed_out}:
        logger.warning(
            "视频任务终止目标非法 task_id=%s current_status=%s target_status=%s event_type=%s",
            task.id,
            task.status.value,
            target.value,
            event_type,
        )
        raise ValueError("任务终止只能进入 failed、cancelled 或 timed_out")
    locked_task = VideoTaskCrud(session).get_for_update(task_id=task.id)
    if locked_task is None or locked_task.status in _TERMINAL_TASK_STATUSES:
        return False
    if target == VideoTaskStatus.timed_out and locked_task.status not in _TIMEOUTABLE_TASK_STATUSES:
        return False
    error_snapshot = {"code": error_code, "message": error_message}
    usage = UsageApplicationService(session).refund_resource(
        resource_type="video_task",
        resource_id=locked_task.id,
        reason="视频生成失败退款",
        public_response_payload=_public_task_response_payload(locked_task, status=target, error_payload=error_snapshot),
        upstream_response_payload=upstream_response_payload,
    )
    if usage is None:
        return False
    locked_task.error_payload = error_snapshot
    _transition_task(session, task=locked_task, target=target, event_type=event_type, payload=locked_task.error_payload)
    release_task_concurrency(session, task_id=locked_task.id)
    logger.warning(
        "视频任务终止并释放预占待事务提交 task_id=%s target_status=%s event_type=%s error_code=%s error_message=%s charge_found=%s",
        locked_task.id,
        target.value,
        event_type,
        error_code,
        error_message,
        usage is not None,
    )
    return True


def _settle_polled_task(session: Session, *, task: VideoTask, result_url: str | None, result_payload: dict) -> bool:
    """在同一事务中结算已被上游确认成功的视频任务。"""

    locked_task = VideoTaskCrud(session).get_for_update(task_id=task.id)
    if locked_task is None or locked_task.status not in {VideoTaskStatus.queued, VideoTaskStatus.processing}:
        return False
    locked_task.result_url = result_url
    locked_task.result_payload = dict(result_payload)
    locked_task.progress = 100
    _transition_task(session, task=locked_task, target=VideoTaskStatus.succeeded, event_type="provider_succeeded")
    public_response_payload = _public_task_response_payload(locked_task)
    usage = UsageApplicationService(session).settle_resource(
        resource_type="video_task",
        resource_id=locked_task.id,
        public_response_payload=public_response_payload,
        upstream_response_payload=result_payload,
    )
    if usage is None:
        raise RuntimeError("视频任务缺少可结算的使用记录")
    release_task_concurrency(session, task_id=locked_task.id)
    return True


async def _cancel_video_task_by_admin(
    session: Session, *, task_id: UUID, admin_id: str, reason: str
) -> VideoTask | None:
    """由管理员取消未终态视频任务，并统一释放仍处于预占状态的资金。

    参数为任务标识、管理员审计标识及安全取消原因。任务不存在时返回空；已终态或已失去资金裁决权时返回
    当前任务且不调用 Provider。成功取消会锁定任务和扣费单，调用最近一次成功提交的 Provider，再在同一
    事务写入取消终态、账本冲正和脱敏审计事件；Provider 调用异常向调用方透传以便回滚。
    """

    task_crud = VideoTaskCrud(session)
    task = task_crud.get_for_update(task_id=task_id)
    if task is None or task.status in _TERMINAL_TASK_STATUSES:
        return task
    usage = UsageApplicationService(session).refund_resource(
        resource_type="video_task", resource_id=task.id, reason="视频生成取消退款"
    )
    if usage is None:
        return task
    provider_summary: dict[str, object] = {"status": "not_submitted"}
    provider_task_id = getattr(task, "upstream_task_id", None)
    if provider_task_id is not None:
        snapshot = await _get_frozen_channel_provider(session, task=task).cancel(provider_task_id)
        provider_summary = {"status": snapshot.status.value, "progress": snapshot.progress}
    task.error_payload = {"code": "admin_cancelled", "message": reason}
    _transition_task(
        session,
        task=task,
        target=VideoTaskStatus.cancelled,
        event_type="admin_cancelled",
        payload={"admin_id": admin_id, "reason": reason, "provider": provider_summary},
    )
    release_task_concurrency(session, task_id=task.id)
    return task


def to_task_data(task: VideoTask) -> VideoTaskData:
    """将持久化任务转换为安全的内部任务投影。

    参数 ``task`` 为已读取的任务实体，返回不含 Provider 请求快照、配置和认证相关字段的不可变契约；
    不访问数据库，也不会修改任务。HTTP 和管理端适配层负责将该契约转换为各自的响应 DTO。
    """

    input_payload = getattr(task, "input_payload", {})
    model = input_payload.get("model") if isinstance(input_payload, dict) else None
    if model is None:
        model = getattr(task, "model", getattr(task, "model_id", ""))
    return VideoTaskData(
        id=str(task.id),
        model=str(model),
        status=task.status.value,
        progress=float(task.progress),
        created_at=task.created_at,
        completed_at=task.completed_at,
        result_url=None,
        error=_safe_error_payload(task.error_payload),
    )


def to_openai_video_data(
    task: VideoTask,
    *,
    result_url: str | None = None,
    balance: str | None = None,
) -> OpenAIVideoData:
    input_payload = getattr(task, "input_payload", {})
    if not isinstance(input_payload, dict):
        input_payload = {}
    status = {
        VideoTaskStatus.submitting: "queued",
        VideoTaskStatus.queued: "queued",
        VideoTaskStatus.submission_unknown: "in_progress",
        VideoTaskStatus.processing: "in_progress",
        VideoTaskStatus.succeeded: "completed",
        VideoTaskStatus.failed: "failed",
        VideoTaskStatus.cancelled: "failed",
        VideoTaskStatus.timed_out: "failed",
    }[task.status]
    return OpenAIVideoData(
        id=f"task_{task.id}",
        model=str(input_payload.get("model", task.model_id)),
        status=status,
        progress=max(0, min(100, int(task.progress))),
        created_at=task.created_at or datetime.now(UTC),
        result_url=result_url,
        error=_safe_error_payload(task.error_payload),
        cost=_pricing_amount(getattr(task, "pricing_snapshot", None)),
        balance=balance,
        reference_tokens=_reference_tokens(getattr(task, "pricing_snapshot", None)),
    )


def _delivers_external_result(task: VideoTask) -> bool:
    """判断任务冻结快照是否标记为“上游直链交付成品”，此类任务平台不做本地化。"""

    execution_snapshot = task.execution_snapshot
    if not isinstance(execution_snapshot, dict):
        return False
    return execution_snapshot.get(RESULT_DELIVERY_KEY) == RESULT_DELIVERY_EXTERNAL


def _public_task_response_payload(
    task: VideoTask,
    *,
    status: VideoTaskStatus | None = None,
    error_payload: dict | None = None,
) -> dict:
    input_payload = getattr(task, "input_payload", {})
    model = input_payload.get("model") if isinstance(input_payload, dict) else None
    if model is None:
        model = getattr(task, "model", getattr(task, "model_id", ""))
    created_at = getattr(task, "created_at", None)
    completed_at = getattr(task, "completed_at", None)
    resolved_status = status or task.status
    resolved_error = error_payload if error_payload is not None else getattr(task, "error_payload", None)
    return {
        "id": str(task.id),
        "model": str(model),
        "status": resolved_status.value,
        "progress": float(task.progress),
        "created_at": created_at.isoformat() if created_at is not None else None,
        "completed_at": completed_at.isoformat() if completed_at is not None else None,
        "result_url": getattr(task, "result_url", None),
        "error": _safe_error_payload(resolved_error),
    }


def _pricing_amount(pricing_snapshot: object) -> str | None:
    if not isinstance(pricing_snapshot, dict):
        return None
    amount = pricing_snapshot.get("amount")
    return amount if isinstance(amount, str) else None


def _reference_tokens(pricing_snapshot: object) -> str | None:
    """回显报价快照中参考素材计费项的可计费 token 数。

    仅按参考素材计量计费的模型（如 fal MiniMax H3 Max 参考生视频）会产生该计费项，其余模型返回空值。
    """

    tokens = chargeable_material_tokens(pricing_snapshot)
    return None if tokens is None else str(tokens)


def _safe_error_payload(payload: object) -> dict[str, object] | None:
    """将任务错误限制为稳定的公开字段，隔离历史或内部诊断数据。"""

    if not isinstance(payload, dict):
        return None
    code = payload.get("code")
    if not isinstance(code, str) or not _PUBLIC_ERROR_CODE_PATTERN.fullmatch(code):
        return None
    return {"code": code, "message": _public_error_message(payload.get("message"))}


def _provider_error_details(
    payload: object,
    *,
    fallback_code: str,
    fallback_message: str,
) -> tuple[str, str]:
    source = payload.get("error") if isinstance(payload, dict) and isinstance(payload.get("error"), dict) else payload
    if not isinstance(source, dict):
        return fallback_code, _public_error_message(fallback_message)
    code = source.get("code")
    message = source.get("message")
    return (
        code if isinstance(code, str) and _PUBLIC_ERROR_CODE_PATTERN.fullmatch(code) else fallback_code,
        _public_error_message(message if isinstance(message, str) else fallback_message),
    )


def _public_error_message(value: object) -> str:
    message = _extract_error_message(value)
    if not message or len(message) > _ERROR_MESSAGE_MAX_LENGTH:
        return "任务处理失败"
    if _SENSITIVE_ERROR_MESSAGE_PATTERN.search(message) or _INTERNAL_ERROR_MESSAGE_PATTERN.search(message):
        return "任务处理失败"
    normalized = message.lower()
    if "input_reference" in normalized and "images" in normalized:
        return "input_reference 和 images 不能同时提供"
    if any(term in normalized for term in ("missing", "required", "必填", "缺少")):
        return "缺少必填参数"
    if any(term in normalized for term in ("unsupported", "format", "格式不支持")):
        return "输入文件格式不支持"
    if any(term in normalized for term in ("invalid", "out of range", "参数不合法", "参数值")):
        return "参数值不合法"
    return message


def _extract_error_message(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    message = value.strip()
    if not message:
        return None
    try:
        decoded = json.loads(message)
    except json.JSONDecodeError:
        return message
    if not isinstance(decoded, dict):
        return message
    for key in ("detail", "message"):
        detail = decoded.get(key)
        if isinstance(detail, str) and detail.strip():
            return detail.strip()
    return message


async def _submit_video_task(session: Session, *, task: VideoTask) -> VideoTask:
    command = CreateVideoCommand(str(task.id), task.execution_snapshot["provider_request"])
    provider_type = task.execution_snapshot.get("provider_type", "unknown")
    logger.info(
        "视频任务提交开始",
        extra={"task_id": task.id, "model_id": task.model_id, "provider_type": provider_type},
    )
    try:
        submission = await _get_frozen_channel_provider(session, task=task).submit(command)
    except ProviderError as exc:
        logger.warning(
            "视频任务提交失败",
            extra={
                "task_id": task.id,
                "model_id": task.model_id,
                "provider_type": provider_type,
                "error_code": exc.code,
                "error_message": str(exc),
                "retryable": exc.retryable,
            },
        )
        if exc.retryable:
            task.error_payload = {"code": exc.code, "message": str(exc)}
            if task.status == VideoTaskStatus.submitting:
                task.status = VideoTaskStatus.submission_unknown
                VideoTaskCrud(session).add_event(
                    TaskEvent(
                        task_id=task.id,
                        from_status="submitting",
                        to_status="submission_unknown",
                        event_type="submission_unknown",
                        payload={"code": exc.code},
                    )
                )
            return task
        error_code, error_message = _provider_error_details(
            exc.response_body,
            fallback_code=exc.code,
            fallback_message=str(exc),
        )
        _terminate_task_and_release_charge(
            session,
            task=task,
            target=VideoTaskStatus.failed,
            event_type="provider_submit_failed",
            error_code=error_code,
            error_message=error_message,
            upstream_response_payload=exc.response_body,
        )
        return task
    task.upstream_task_id = submission.upstream_task_id
    task.submission_response = submission.raw
    task.submitted_at = datetime.now(UTC)
    _transition_task(
        session,
        task=task,
        target=VideoTaskStatus.processing if submission.status.value == "processing" else VideoTaskStatus.queued,
        event_type="provider_submitted",
    )
    UsageApplicationService(session).update_resource_response(
        resource_type="video_task",
        resource_id=task.id,
        public_response_payload=_public_task_response_payload(task),
        upstream_response_payload=submission.raw,
    )
    logger.info(
        "视频任务提交成功",
        extra={"task_id": task.id, "provider_type": provider_type, "upstream_task_id": submission.upstream_task_id},
    )
    return task


class VideoApplicationService:
    def __init__(self, session: Session) -> None:
        self._session = session

    async def create_task(
        self,
        *,
        user_id: UUID,
        group_ids: list[int],
        access_token_id: UUID,
        token_display_name: str | None,
        request: dict,
    ) -> VideoTask:
        try:
            task = _create_video_task(
                self._session,
                user_id=user_id,
                group_ids=group_ids,
                access_token_id=access_token_id,
                token_display_name=token_display_name,
                request=request,
            )
            if task.status == VideoTaskStatus.submitting:
                await _submit_video_task(self._session, task=task)
            self._session.commit()
            VideoTaskCrud(self._session).refresh(task)
            return task
        except ProviderError as exc:
            self._session.rollback()
            raise ValidationError("上游视频任务提交失败") from exc
        except ValueError as exc:
            self._session.rollback()
            raise ValidationError(str(exc), **error_context(exc)) from exc
        except Exception:
            self._session.rollback()
            raise

    def list_tasks(self, *, user_id: UUID) -> list[VideoTask]:
        return _list_video_tasks(self._session, user_id=user_id)

    def get_owned_task(self, *, task_id: UUID, user_id: UUID) -> VideoTask:
        task = _get_owned_video_task(self._session, task_id=task_id, user_id=user_id)
        if task is None:
            raise NotFoundError("视频任务不存在")
        return task

    async def create_openai_video(
        self,
        *,
        user_id: UUID,
        group_ids: list[int],
        access_token_id: UUID,
        token_display_name: str | None,
        request: dict,
    ) -> OpenAIVideoData:
        task = await self.create_task(
            user_id=user_id,
            group_ids=group_ids,
            access_token_id=access_token_id,
            token_display_name=token_display_name,
            request=request,
        )
        return to_openai_video_data(task)

    def get_owned_openai_video(self, *, video_id: UUID, user_id: UUID) -> OpenAIVideoData:
        return to_openai_video_data(self.get_owned_task(task_id=video_id, user_id=user_id))

    async def get_owned_video_content(self, *, video_id: UUID, user_id: UUID, variant: str):
        task = self.get_owned_completed_video_task(video_id=video_id, user_id=user_id, variant=variant)
        try:
            return await _get_frozen_channel_provider(self._session, task=task).fetch_result(task.upstream_task_id)
        except ProviderError as exc:
            raise ValidationError("视频成品暂不可下载") from exc

    def get_owned_completed_video_task(self, *, video_id: UUID, user_id: UUID, variant: str) -> VideoTask:
        if variant != "video":
            raise ValidationError("当前视频不支持该成品类型")
        task = self.get_owned_task(task_id=video_id, user_id=user_id)
        if task.status != VideoTaskStatus.succeeded or not task.upstream_task_id:
            raise ValidationError("视频成品尚不可下载")
        return task

    async def cancel_task_by_admin(self, *, task_id: UUID, admin_id: str, reason: str) -> VideoTask:
        try:
            task = await _cancel_video_task_by_admin(self._session, task_id=task_id, admin_id=admin_id, reason=reason)
            if task is None:
                raise NotFoundError("视频任务不存在")
            self._session.commit()
            return task
        except ProviderError as exc:
            self._session.rollback()
            raise ValidationError("上游取消请求失败") from exc
        except Exception:
            self._session.rollback()
            raise
