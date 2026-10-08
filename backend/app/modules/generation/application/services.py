"""图片与文本同步生成用例编排。

本模块负责解析公开模型、校验请求、选择渠道、冻结计费决策并同步调用上游 Provider；它复用视频模块
共享的模型、渠道与定价数据访问，以及全局钱包和使用记录服务，不直接执行 SQL 或持久化语句。
"""

import asyncio
import base64
import json
import logging
import re
from collections import defaultdict
from collections.abc import AsyncIterator
from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal
from time import perf_counter
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.bootstrap.container import get_channel_provider_factory, get_provider_template_registry
from app.core.errors import (
    ApplicationError,
    UpstreamTimeoutError,
    UpstreamUnavailableError,
    ValidationError,
    error_context,
)
from app.core.protocols import model_operations
from app.modules.channels.application.concurrency import (
    release_task_concurrency,
    reserve_task_concurrency,
)
from app.modules.channels.application.model_mapping import apply_upstream_model_name
from app.modules.channels.application.routing import select_channel_in_group_order
from app.modules.channels.crud.channels import ChannelCrud
from app.modules.channels.runtime.routing_snapshot import get_generation_configuration_snapshot
from app.modules.generation.application.contracts import GenerationBilling, PreparedGeneration
from app.modules.pricing.application.engine import (
    MaterialFacts,
    list_unpriced_groups,
    missing_pricing_rule_message,
    quote_pricing,
    select_pricing_plan,
)
from app.modules.pricing.model.pricing_item import PricingItemKind
from app.modules.providers.anthropic import (
    ENDPOINT_FIELD as ANTHROPIC_ENDPOINT_FIELD,
)
from app.modules.providers.anthropic import (
    PROVIDER_NAME as ANTHROPIC_PROVIDER_NAME,
)
from app.modules.providers.contracts import (
    GenerationProvider,
    ProviderError,
    ProviderUpload,
)
from app.modules.usage.application.normalization import normalize_image_usage, normalize_text_usage
from app.modules.usage.application.services import UsageApplicationService
from app.modules.user.crud.token_group_crud import TokenGroupCrud

logger = logging.getLogger(__name__)

_TOKEN_KINDS = {
    PricingItemKind.input_text_tokens.value,
    PricingItemKind.cached_input_text_tokens.value,
    PricingItemKind.output_text_tokens.value,
}
_IMAGE_TOKEN_KINDS = {
    PricingItemKind.input_image_tokens.value,
    PricingItemKind.output_image_tokens.value,
}
_SUPPORTED_FIELD_TYPES = {"string", "integer", "number", "boolean", "array", "object"}
_ALLOWED_IMAGE_FIELDS = {"image", "mask"}
_MAX_UPLOAD_BYTES = 20 * 1024 * 1024
_MAX_IMAGE_UPLOADS = 16
_MAX_SSE_PENDING_BYTES = 1024 * 1024


def _provider_application_error(error: ProviderError, resource: str) -> ApplicationError:
    details = {"upstream_code": error.code, "upstream_message": str(error)}
    if error.code == "timeout":
        return UpstreamTimeoutError(f"上游{resource}服务请求超时", **details)
    return UpstreamUnavailableError(f"上游{resource}服务调用失败", **details)


def _load_generation_configuration(channel_crud, *, model_name: str, model_type: str, group_ids: list[int]):
    model = channel_crud.get_active_model(name=model_name, model_type=model_type)
    if model is None:
        return None, [], ([], [], [])
    return (
        model,
        channel_crud.list_channels_for_model(model_id=model.id, group_ids=group_ids),
        channel_crud.list_pricing_configuration(model_id=model.id),
    )


class _GenerationServiceBase:
    """图片与文本同步生成共享的选路、报价与结算编排。"""

    _MODEL_TYPE: str
    _REQUEST_TYPE: str
    _RESOURCE_TYPE: str
    _RESERVE_REASON: str

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def _prepare(
        self,
        *,
        user_id: UUID,
        group_ids: list[int],
        access_token_id: UUID,
        token_display_name: str | None,
        payload: dict[str, Any],
        uploads: list[ProviderUpload] | None = None,
        validate_provider_request: Any = None,
    ) -> PreparedGeneration:
        """在短事务内完成选路、契约校验、计费预占和并发占用。"""

        async with self._session_factory() as session:
            return await session.run_sync(
                self._prepare_sync,
                user_id,
                group_ids,
                access_token_id,
                token_display_name,
                payload,
                uploads or [],
                validate_provider_request,
            )

    @classmethod
    def _prepare_sync(
        cls,
        sync_session,
        user_id: UUID,
        group_ids: list[int],
        access_token_id: UUID,
        token_display_name: str | None,
        payload: dict[str, Any],
        uploads: list[ProviderUpload],
        validate_provider_request: Any = None,
    ) -> PreparedGeneration:
        try:
            prepared = cls._build_preparation(
                sync_session,
                user_id=user_id,
                group_ids=group_ids,
                access_token_id=access_token_id,
                token_display_name=token_display_name,
                payload=payload,
                uploads=uploads,
                validate_provider_request=validate_provider_request,
            )
            sync_session.commit()
            return prepared
        except ValueError as exc:
            sync_session.rollback()
            raise ValidationError(str(exc), **error_context(exc)) from exc
        except Exception:
            sync_session.rollback()
            raise

    @classmethod
    def _build_preparation(
        cls,
        sync_session,
        *,
        user_id: UUID,
        group_ids: list[int],
        access_token_id: UUID,
        token_display_name: str | None,
        payload: dict[str, Any],
        uploads: list[ProviderUpload],
        validate_provider_request: Any = None,
    ) -> PreparedGeneration:
        model_name = payload.get("model")
        if not isinstance(model_name, str) or not model_name:
            raise ValueError("model 必须是字符串")
        channel_crud = ChannelCrud(sync_session)
        configuration = get_generation_configuration_snapshot(
            model_name=model_name,
            model_type=cls._MODEL_TYPE,
            group_ids=group_ids,
            loader=lambda: _load_generation_configuration(
                channel_crud, model_name=model_name, model_type=cls._MODEL_TYPE, group_ids=group_ids
            ),
        )
        if configuration is None:
            raise ValueError("未配置当前公开模型")
        model = configuration.model
        contract = model.input_contract
        input_schema = contract.get("input_schema") if isinstance(contract, dict) else None
        if not isinstance(input_schema, dict):
            raise ValueError("模型请求契约不合法")
        normalized = _normalize_payload(payload, input_schema)
        derived_pricing_fields = _derived_pricing_fields(contract)
        _reject_client_derived_fields(normalized, derived_pricing_fields)
        channels = list(configuration.channels)
        rules = list(configuration.rules)
        items = list(configuration.items)
        modifiers = list(configuration.modifiers)
        pricing_context = cls._pricing_context(normalized, derived_pricing_fields)
        pricing_context["input_image_dimensions"] = [
            _image_dimensions(upload.content) for upload in uploads if upload.field_name in _ALLOWED_IMAGE_FIELDS
        ]
        created_at = datetime.now(UTC)
        route = None
        plan = None
        attempted = False
        unmatched_group_ids: list[int] = []
        for candidate in select_channel_in_group_order(channels, group_ids=group_ids):
            attempted = True
            try:
                candidate_plan = select_pricing_plan(
                    rules,
                    context=pricing_context,
                    allowed_fields=list(model.pricing_fields),
                    group_ids=[candidate.binding.token_group_id],
                    created_at=created_at,
                )
            except ValueError:
                unmatched_group_ids.append(candidate.binding.token_group_id)
                continue
            route, plan = candidate, candidate_plan
            break
        if route is None or plan is None:
            if not attempted:
                raise ValueError("当前模型没有可用渠道")
            unpriced_group_ids = list_unpriced_groups(rules, group_ids=unmatched_group_ids)
            if unpriced_group_ids:
                raise ValueError(missing_pricing_rule_message(model_name=model.name, group_ids=unpriced_group_ids))
            raise ValueError("主分组与兜底分组均没有可匹配的计费方案")
        channel = route.channel
        selected_group = TokenGroupCrud(sync_session).get_group(route.binding.token_group_id)
        group_multiplier = selected_group.price_multiplier if selected_group is not None else Decimal("1.000000")
        group_multipliers = {route.binding.token_group_id: group_multiplier}
        template = get_provider_template_registry().get(model.template_id)
        if template is None:
            raise ValueError("模型模板不存在")
        provider_request = _provider_request(normalized, derived_pricing_fields)
        apply_upstream_model_name(provider_request, channel.model_mapping.get(model.name))
        provider_request.update(deepcopy(channel.param_override))
        if template["provider_type"] != ANTHROPIC_PROVIDER_NAME:
            # 端点标记仅供 anthropic 适配器选择调用形状，转发前从其它 Provider 的请求体剥离。
            provider_request.pop(ANTHROPIC_ENDPOINT_FIELD, None)
        provider = get_channel_provider_factory().get_frozen_generation_provider(
            {
                "route_id": str(route.binding.id),
                "base_url": channel.base_url,
                "config": {**template.get("provider_config", {}), **dict(channel.config)},
            },
            provider_type=template["provider_type"],
            api_key=channel.api_key,
        )
        (validate_provider_request or cls._validate_provider_request)(provider, provider_request)
        plan_items = [item for item in items if item.pricing_rule_id == plan.id and item.active]
        plan_modifiers = [modifier for modifier in modifiers if modifier.pricing_rule_id == plan.id]
        postpaid = any(item.kind in _TOKEN_KINDS | _IMAGE_TOKEN_KINDS for item in plan_items)
        reserved_amount = Decimal(0)
        decision = None
        if not postpaid:
            decision = quote_pricing(
                rules,
                _group_by_rule(items),
                _group_by_rule(modifiers),
                context=pricing_context,
                facts=MaterialFacts(),
                allowed_fields=list(model.pricing_fields),
                group_ids=[route.binding.token_group_id],
                created_at=created_at,
                group_multipliers=group_multipliers,
            )
            reserved_amount = decision.amount
        resource_id = uuid4()
        reserve_task_concurrency(sync_session, task_id=resource_id, user_id=user_id, model_id=model.id)
        billing = GenerationBilling(
            user_id=user_id,
            access_token_id=access_token_id,
            token_display_name=token_display_name,
            token_group_id=route.binding.token_group_id,
            resource_id=resource_id,
            request_type=cls._REQUEST_TYPE,
            resource_type=cls._RESOURCE_TYPE,
            model_id=model.id,
            model_name=model.name,
            channel_id=channel.id,
            channel_name=channel.name,
            provider_name=template["provider_type"],
            request_payload=dict(payload),
            group_ids=[route.binding.token_group_id],
            postpaid=postpaid,
            reserved_amount=reserved_amount,
            pricing_context=pricing_context,
            priced_at=created_at,
            token_group_price_multiplier=group_multiplier,
            plan=plan,
            items=list(plan_items),
            modifiers=list(plan_modifiers),
            allowed_fields=list(model.pricing_fields),
        )
        if not postpaid:
            UsageApplicationService(sync_session).create_reserved(
                user_id=user_id,
                access_token_id=access_token_id,
                token_display_name=token_display_name,
                token_group_id=route.binding.token_group_id,
                request_id=str(resource_id),
                request_type=cls._REQUEST_TYPE,
                resource_type=cls._RESOURCE_TYPE,
                resource_id=resource_id,
                model_id=model.id,
                model_name=model.name,
                channel_id=channel.id,
                channel_name=channel.name,
                provider_name=template["provider_type"],
                request_payload=dict(payload),
                amount=reserved_amount,
                reason=cls._RESERVE_REASON,
                response_metadata={"pricing": decision.snapshot} if decision is not None else None,
            )
        return PreparedGeneration(
            provider=provider, provider_request=provider_request, billing=billing, uploads=list(uploads)
        )

    @staticmethod
    def _validate_provider_request(provider: GenerationProvider, provider_request: dict[str, Any]) -> None:
        raise NotImplementedError

    @staticmethod
    def _pricing_context(normalized: dict[str, Any], derived_pricing_fields: list[dict[str, Any]]) -> dict[str, Any]:
        return dict(normalized)

    async def _finalize(
        self,
        prepared: PreparedGeneration,
        *,
        success: bool,
        usage: dict[str, Any] | None,
        upstream_payload: dict[str, Any] | None,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        duration_ms: int | None = None,
        first_token_duration_ms: int | None = None,
    ) -> None:
        """在短事务内结算或退款，并释放并发占用。"""

        async with self._session_factory() as session:
            await session.run_sync(
                _finalize_sync,
                prepared,
                success,
                usage,
                upstream_payload,
                started_at,
                completed_at,
                duration_ms,
                first_token_duration_ms,
            )

    async def _finalize_cancelled(self, prepared: PreparedGeneration) -> None:
        """协程被取消时以可屏蔽取消的方式收尾，避免预占资金与并发租约悬空。"""

        try:
            await asyncio.shield(self._finalize(prepared, success=False, usage=None, upstream_payload=None))
        except Exception:
            logger.exception("生成请求取消后收尾失败 resource_id=%s", prepared.billing.resource_id)


def _finalize_sync(
    sync_session,
    prepared: PreparedGeneration,
    success: bool,
    usage: dict[str, Any] | None,
    upstream_payload: dict[str, Any] | None,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
    duration_ms: int | None = None,
    first_token_duration_ms: int | None = None,
) -> None:
    billing = prepared.billing
    try:
        if billing.postpaid:
            _finalize_postpaid(
                sync_session,
                billing,
                success=success,
                usage=usage,
                upstream_payload=upstream_payload,
                started_at=started_at,
                completed_at=completed_at,
                duration_ms=duration_ms,
                first_token_duration_ms=first_token_duration_ms,
            )
        elif success:
            UsageApplicationService(sync_session).settle_resource(
                resource_type=billing.resource_type,
                resource_id=billing.resource_id,
                public_response_payload=upstream_payload,
                upstream_response_payload=upstream_payload,
            )
        else:
            UsageApplicationService(sync_session).refund_resource(
                resource_type=billing.resource_type,
                resource_id=billing.resource_id,
                reason="同步生成调用失败退款",
                upstream_response_payload=upstream_payload,
            )
        release_task_concurrency(sync_session, task_id=billing.resource_id)
        sync_session.commit()
    except Exception:
        sync_session.rollback()
        raise


def _finalize_postpaid(
    sync_session,
    billing: GenerationBilling,
    *,
    success: bool,
    usage: dict[str, Any] | None,
    upstream_payload: dict[str, Any] | None,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
    duration_ms: int | None = None,
    first_token_duration_ms: int | None = None,
) -> None:
    """按上游实际用量后付费扣费；失败时记录零金额调用。"""

    image_token_billing = any(item.kind in _IMAGE_TOKEN_KINDS for item in billing.items)
    if not success:
        logger.warning(
            "后付费调用失败，记录零金额调用 resource_id=%s has_usage=%s",
            billing.resource_id,
            usage is not None,
        )
        UsageApplicationService(sync_session).create_failed_postpaid(
            user_id=billing.user_id,
            access_token_id=billing.access_token_id,
            token_display_name=billing.token_display_name,
            token_group_id=billing.token_group_id,
            request_id=str(billing.resource_id),
            request_type=billing.request_type,
            resource_type=billing.resource_type,
            resource_id=billing.resource_id,
            model_id=billing.model_id,
            model_name=billing.model_name,
            channel_id=billing.channel_id,
            channel_name=billing.channel_name,
            provider_name=billing.provider_name,
            request_payload=billing.request_payload,
            response_metadata={"outcome": "failed"},
            upstream_response_payload=upstream_payload,
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=duration_ms,
            first_token_duration_ms=first_token_duration_ms,
        )
        return
    if usage is None and not image_token_billing:
        logger.warning(
            "文本后付费未产生扣费 resource_id=%s reason=missing_usage",
            billing.resource_id,
        )
        return
    context = dict(billing.pricing_context)
    if image_token_billing:
        normalized_image_usage = normalize_image_usage(usage or {})
        if normalized_image_usage is None:
            _estimate_image_usage(context, billing.items, upstream_payload, provider_name=billing.provider_name)
        else:
            context["image_input_tokens"] = normalized_image_usage.input_tokens
            context["image_output_tokens"] = normalized_image_usage.output_tokens
            context["image_input_tokens_source"] = "upstream"
            context["image_output_tokens_source"] = "upstream"
        prompt_tokens = context.get("image_input_tokens")
        completion_tokens = context.get("image_output_tokens")
        cached_tokens = None
        cache_write_tokens = None
        reason = "图片生成 Token 调用扣费"
    else:
        normalized_usage = normalize_text_usage(usage)
        if normalized_usage is None:
            logger.warning("文本后付费未产生扣费 resource_id=%s reason=invalid_usage", billing.resource_id)
            return
        context["prompt_tokens"] = normalized_usage.prompt_tokens
        context["completion_tokens"] = normalized_usage.completion_tokens
        context["cached_tokens"] = normalized_usage.cached_tokens
        context["cache_write_tokens"] = normalized_usage.cache_write_tokens
        prompt_tokens = normalized_usage.prompt_tokens
        completion_tokens = normalized_usage.completion_tokens
        cached_tokens = normalized_usage.cached_tokens
        cache_write_tokens = normalized_usage.cache_write_tokens
        reason = "文本生成调用扣费"
    decision = quote_pricing(
        [billing.plan],
        {billing.plan.id: billing.items},
        {billing.plan.id: billing.modifiers},
        context=context,
        facts=MaterialFacts(),
        allowed_fields=billing.allowed_fields,
        group_ids=billing.group_ids,
        created_at=billing.priced_at,
        group_multipliers={billing.token_group_id: billing.token_group_price_multiplier},
    )
    if decision.amount <= 0:
        return
    response_metadata = {
        **({"pricing": decision.snapshot} if isinstance(getattr(decision, "snapshot", None), dict) else {}),
        **(
            {
                "image_token_usage": {
                    "input_tokens": context["image_input_tokens"],
                    "output_tokens": context["image_output_tokens"],
                    "input_source": context["image_input_tokens_source"],
                    "output_source": context["image_output_tokens_source"],
                }
            }
            if image_token_billing
            else {}
        ),
    }
    UsageApplicationService(sync_session).create_settled_postpaid(
        user_id=billing.user_id,
        access_token_id=billing.access_token_id,
        token_display_name=billing.token_display_name,
        token_group_id=billing.token_group_id,
        request_id=str(billing.resource_id),
        request_type=billing.request_type,
        resource_type=billing.resource_type,
        resource_id=billing.resource_id,
        model_id=billing.model_id,
        model_name=billing.model_name,
        channel_id=billing.channel_id,
        channel_name=billing.channel_name,
        provider_name=billing.provider_name,
        request_payload=billing.request_payload,
        amount=decision.amount,
        reason=reason,
        response_metadata=response_metadata,
        public_response_payload=upstream_payload,
        upstream_response_payload=upstream_payload,
        prompt_tokens=prompt_tokens if isinstance(prompt_tokens, int) else None,
        completion_tokens=completion_tokens if isinstance(completion_tokens, int) else None,
        cached_tokens=cached_tokens,
        cache_write_tokens=cache_write_tokens,
        started_at=started_at,
        completed_at=completed_at,
        duration_ms=duration_ms,
        first_token_duration_ms=first_token_duration_ms,
    )


def _estimate_image_usage(
    context: dict[str, Any], items: list[Any], upstream_payload: dict[str, Any] | None, *, provider_name: str
) -> None:
    input_config = _image_estimate_config(items, PricingItemKind.input_image_tokens.value)
    output_config = _image_estimate_config(items, PricingItemKind.output_image_tokens.value)
    text_tokens = _estimated_prompt_tokens(context, input_config)
    input_image_dimensions = _input_image_dimensions(context)
    output_images = _image_output_count(context, upstream_payload)
    image_input_tokens = len(input_image_dimensions) * int(input_config["input_image_tokens_per_image"])
    if provider_name == "gemini":
        image_input_tokens = sum(
            _gemini_image_token_estimate(dimensions, input_config) for dimensions in input_image_dimensions
        )
    context["image_input_tokens"] = text_tokens + image_input_tokens
    context["image_output_tokens"] = output_images * int(output_config["output_image_tokens_per_image"])
    context["image_input_tokens_source"] = "estimated"
    context["image_output_tokens_source"] = "estimated"


def _image_estimate_config(items: list[Any], kind: str) -> dict[str, Any]:
    for item in items:
        if item.kind == kind:
            config = getattr(item, "estimate_config", {})
            if isinstance(config, dict):
                return config
    raise ValueError("图片 Token 计费缺少估算配置")


def _estimated_prompt_tokens(context: dict[str, Any], config: dict[str, Any]) -> int:
    prompt = context.get("prompt")
    text = prompt if isinstance(prompt, str) else _gemini_prompt_text(context.get("contents"))
    ratio = Decimal(str(config["text_chars_per_token"]))
    return int((Decimal(len(text)) / ratio).to_integral_value(rounding="ROUND_CEILING"))


def _gemini_prompt_text(value: Any) -> str:
    if isinstance(value, list):
        return "".join(_gemini_prompt_text(item) for item in value)
    if isinstance(value, dict):
        parts = value.get("parts")
        if isinstance(parts, list):
            return _gemini_prompt_text(parts)
        text = value.get("text")
        return text if isinstance(text, str) else ""
    return ""


def _input_image_dimensions(context: dict[str, Any]) -> list[tuple[int, int] | None]:
    if isinstance(context.get("contents"), list):
        return _gemini_inline_image_dimensions(context["contents"])
    dimensions = context.get("input_image_dimensions")
    if not isinstance(dimensions, list):
        return []
    return [item if _valid_image_dimensions(item) else None for item in dimensions]


def _gemini_inline_image_dimensions(value: Any) -> list[tuple[int, int] | None]:
    if isinstance(value, dict):
        inline_data = value.get("inlineData")
        if isinstance(inline_data, dict):
            encoded = inline_data.get("data")
            return [_image_dimensions_from_base64(encoded)]
        if isinstance(value.get("fileData"), dict):
            return [None]
        return _gemini_inline_image_dimensions(value.get("parts", []))
    if isinstance(value, list):
        return [dimension for item in value for dimension in _gemini_inline_image_dimensions(item)]
    return []


def _gemini_image_token_estimate(dimensions: tuple[int, int] | None, config: dict[str, Any]) -> int:
    tiles = _gemini_image_tiles(dimensions)
    if tiles is None:
        tiles = int(config["gemini_unknown_image_tiles_per_image"])
    return tiles * 258


def _gemini_image_tiles(dimensions: tuple[int, int] | None) -> int | None:
    if dimensions is None:
        return None
    width, height = dimensions
    if width <= 384 and height <= 384:
        return 1
    return ((width + 767) // 768) * ((height + 767) // 768)


def _valid_image_dimensions(value: object) -> bool:
    return (
        isinstance(value, tuple)
        and len(value) == 2
        and all(isinstance(item, int) and not isinstance(item, bool) and item > 0 for item in value)
    )


def _image_dimensions_from_base64(value: object) -> tuple[int, int] | None:
    if not isinstance(value, str):
        return None
    try:
        return _image_dimensions(base64.b64decode(value, validate=True))
    except ValueError:
        return None


def _image_dimensions(content: bytes) -> tuple[int, int] | None:
    if content.startswith(b"\x89PNG\r\n\x1a\n") and len(content) >= 24:
        width = int.from_bytes(content[16:20], "big")
        height = int.from_bytes(content[20:24], "big")
        return (width, height) if width > 0 and height > 0 else None
    if content.startswith((b"GIF87a", b"GIF89a")) and len(content) >= 10:
        width = int.from_bytes(content[6:8], "little")
        height = int.from_bytes(content[8:10], "little")
        return (width, height) if width > 0 and height > 0 else None
    return None


def _image_output_count(context: dict[str, Any], upstream_payload: dict[str, Any] | None) -> int:
    if isinstance(upstream_payload, dict):
        data = upstream_payload.get("data")
        if isinstance(data, list):
            return len(data)
        candidates = upstream_payload.get("candidates")
        if isinstance(candidates, list):
            return len(_gemini_inline_image_dimensions(candidates))
    output_count = context.get("n", 1)
    return output_count if isinstance(output_count, int) and output_count > 0 else 1


class ImageGenerationApplicationService(_GenerationServiceBase):
    """图片生成与图片编辑同步用例。"""

    _MODEL_TYPE = "image"
    _REQUEST_TYPE = "image"
    _RESOURCE_TYPE = "image_generation"
    _RESERVE_REASON = "图片生成调用扣费"

    @staticmethod
    def _validate_provider_request(provider: GenerationProvider, provider_request: dict[str, Any]) -> None:
        provider.validate_image_request(provider_request)

    @staticmethod
    def _pricing_context(normalized: dict[str, Any], derived_pricing_fields: list[dict[str, Any]]) -> dict[str, Any]:
        context = dict(normalized)
        for declaration in derived_pricing_fields:
            if not isinstance(declaration, dict):
                continue
            derived_type = declaration.get("type")
            size_source = declaration.get("size_source")
            if derived_type != "image_pixel_count" or not isinstance(size_source, str):
                continue
            pixel_count = _image_pixel_count(context.get(size_source))
            if pixel_count is not None:
                context[derived_type] = pixel_count
        return context

    async def generate_image(
        self,
        *,
        user_id: UUID,
        group_ids: list[int],
        access_token_id: UUID,
        token_display_name: str | None,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """同步生成图片并返回上游响应体。"""

        prepared = await self._prepare(
            user_id=user_id,
            group_ids=group_ids,
            access_token_id=access_token_id,
            token_display_name=token_display_name,
            payload=payload,
        )
        return await self._execute(prepared)

    async def edit_image(
        self,
        *,
        user_id: UUID,
        group_ids: list[int],
        access_token_id: UUID,
        token_display_name: str | None,
        payload: dict[str, Any],
        uploads: list[ProviderUpload],
    ) -> dict[str, Any]:
        """同步编辑图片并返回上游响应体。"""

        _validate_image_uploads(uploads)
        prepared = await self._prepare(
            user_id=user_id,
            group_ids=group_ids,
            access_token_id=access_token_id,
            token_display_name=token_display_name,
            payload=payload,
            uploads=uploads,
        )
        return await self._execute(prepared)

    async def _execute(self, prepared: PreparedGeneration) -> dict[str, Any]:
        try:
            if prepared.uploads:
                result = await prepared.provider.edit_image(prepared.provider_request, prepared.uploads)
            else:
                result = await prepared.provider.generate_image(prepared.provider_request)
        except asyncio.CancelledError:
            await self._finalize_cancelled(prepared)
            raise
        except ProviderError as exc:
            await self._finalize(prepared, success=False, usage=None, upstream_payload=exc.response_body)
            raise _provider_application_error(exc, "图片") from exc
        await self._finalize(
            prepared,
            success=True,
            usage=_response_usage(result),
            upstream_payload=summarize_upstream_payload(result),
        )
        return result


class TextGenerationApplicationService(_GenerationServiceBase):
    """文本对话同步与流式补全用例。"""

    _MODEL_TYPE = "text"
    _REQUEST_TYPE = "text"
    _RESOURCE_TYPE = "text_generation"
    _RESERVE_REASON = "文本生成调用扣费"

    @staticmethod
    def _validate_provider_request(provider: GenerationProvider, provider_request: dict[str, Any]) -> None:
        provider.validate_chat_request(provider_request)

    @staticmethod
    def _validate_response_provider_request(provider: GenerationProvider, provider_request: dict[str, Any]) -> None:
        provider.validate_response_request(provider_request)

    async def chat(
        self,
        *,
        user_id: UUID,
        group_ids: list[int],
        access_token_id: UUID,
        token_display_name: str | None,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """同步文本补全并返回上游响应体。"""

        prepared = await self._prepare(
            user_id=user_id,
            group_ids=group_ids,
            access_token_id=access_token_id,
            token_display_name=token_display_name,
            payload=payload,
        )
        started_at = datetime.now(UTC)
        started_at_counter = perf_counter()
        try:
            result = await prepared.provider.chat(prepared.provider_request)
        except asyncio.CancelledError:
            await self._finalize_cancelled(prepared)
            raise
        except ProviderError as exc:
            await self._finalize(prepared, success=False, usage=None, upstream_payload=exc.response_body)
            raise _provider_application_error(exc, "文本") from exc
        usage = _response_usage(result)
        completed_at = datetime.now(UTC)
        duration_ms = _duration_ms(started_at_counter)
        await self._finalize(
            prepared,
            success=True,
            usage=usage,
            upstream_payload=summarize_upstream_payload(result),
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=duration_ms,
            first_token_duration_ms=duration_ms if _has_response_text(result) else None,
        )
        return result

    async def chat_stream(
        self,
        *,
        user_id: UUID,
        group_ids: list[int],
        access_token_id: UUID,
        token_display_name: str | None,
        payload: dict[str, Any],
    ) -> tuple[AsyncIterator[bytes], str]:
        """打开流式文本补全，按流结束时的用量结算。"""

        prepared = await self._prepare(
            user_id=user_id,
            group_ids=group_ids,
            access_token_id=access_token_id,
            token_display_name=token_display_name,
            payload=_ensure_stream_usage(payload),
        )
        started_at = datetime.now(UTC)
        started_at_counter = perf_counter()
        try:
            stream, content_type = await prepared.provider.open_chat_stream(prepared.provider_request)
        except asyncio.CancelledError:
            await self._finalize_cancelled(prepared)
            raise
        except ProviderError as exc:
            await self._finalize(prepared, success=False, usage=None, upstream_payload=exc.response_body)
            raise _provider_application_error(exc, "文本") from exc
        return self._relay_stream(prepared, stream, started_at, started_at_counter), content_type

    async def chat_stream_native(
        self,
        *,
        user_id: UUID,
        group_ids: list[int],
        access_token_id: UUID,
        token_display_name: str | None,
        payload: dict[str, Any],
    ) -> tuple[AsyncIterator[bytes], str]:
        """打开厂商原生流式响应，按流结束时的用量结算。

        与 ``chat_stream`` 的差异是不注入 OpenAI 专用的 ``stream_options``，请求体原样转发给
        声明原生协议的 Provider（Gemini、Anthropic、DashScope）。
        """

        prepared = await self._prepare(
            user_id=user_id,
            group_ids=group_ids,
            access_token_id=access_token_id,
            token_display_name=token_display_name,
            payload=payload,
            validate_provider_request=self._validate_provider_request,
        )
        started_at = datetime.now(UTC)
        started_at_counter = perf_counter()
        try:
            stream, content_type = await prepared.provider.open_chat_stream(prepared.provider_request)
        except asyncio.CancelledError:
            await self._finalize_cancelled(prepared)
            raise
        except ProviderError as exc:
            await self._finalize(prepared, success=False, usage=None, upstream_payload=exc.response_body)
            raise _provider_application_error(exc, "文本") from exc
        return self._relay_stream(prepared, stream, started_at, started_at_counter), content_type

    async def create_response(
        self,
        *,
        user_id: UUID,
        group_ids: list[int],
        access_token_id: UUID,
        token_display_name: str | None,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """同步创建 Responses API 响应并返回上游响应体。"""

        prepared = await self._prepare_response(
            user_id=user_id,
            group_ids=group_ids,
            access_token_id=access_token_id,
            token_display_name=token_display_name,
            payload=payload,
        )
        started_at = datetime.now(UTC)
        started_at_counter = perf_counter()
        try:
            result = await prepared.provider.create_response(prepared.provider_request)
        except asyncio.CancelledError:
            await self._finalize_cancelled(prepared)
            raise
        except ProviderError as exc:
            await self._finalize(prepared, success=False, usage=None, upstream_payload=exc.response_body)
            raise _provider_application_error(exc, "文本") from exc
        usage = _response_usage(result)
        completed_at = datetime.now(UTC)
        duration_ms = _duration_ms(started_at_counter)
        await self._finalize(
            prepared,
            success=True,
            usage=usage,
            upstream_payload=summarize_upstream_payload(result),
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=duration_ms,
            first_token_duration_ms=duration_ms if _has_response_text(result) else None,
        )
        return result

    async def response_stream(
        self,
        *,
        user_id: UUID,
        group_ids: list[int],
        access_token_id: UUID,
        token_display_name: str | None,
        payload: dict[str, Any],
    ) -> tuple[AsyncIterator[bytes], str]:
        """打开 Responses API 流式响应，按流结束时的用量结算。"""

        prepared = await self._prepare_response(
            user_id=user_id,
            group_ids=group_ids,
            access_token_id=access_token_id,
            token_display_name=token_display_name,
            payload=payload,
        )
        started_at = datetime.now(UTC)
        started_at_counter = perf_counter()
        try:
            stream, content_type = await prepared.provider.open_response_stream(prepared.provider_request)
        except asyncio.CancelledError:
            await self._finalize_cancelled(prepared)
            raise
        except ProviderError as exc:
            await self._finalize(prepared, success=False, usage=None, upstream_payload=exc.response_body)
            raise _provider_application_error(exc, "文本") from exc
        return self._relay_stream(prepared, stream, started_at, started_at_counter), content_type

    async def _prepare_response(self, **kwargs: Any) -> PreparedGeneration:
        return await self._prepare(validate_provider_request=self._validate_response_provider_request, **kwargs)

    def _relay_stream(
        self,
        prepared: PreparedGeneration,
        stream: AsyncIterator[bytes],
        started_at: datetime,
        started_at_counter: float,
    ) -> AsyncIterator[bytes]:
        """转发上游字节流，并在结束时按实际用量结算。"""

        async def relay() -> AsyncIterator[bytes]:
            usage: dict[str, Any] | None = None
            completed = False
            pending = b""
            first_token_duration_ms: int | None = None
            try:
                async for chunk in stream:
                    if first_token_duration_ms is None and _stream_chunk_has_text(pending, chunk):
                        first_token_duration_ms = _duration_ms(started_at_counter)
                    pending, found = _consume_stream_usage(pending, chunk)
                    if found is not None:
                        usage = found
                    yield chunk
                tail = _usage_from_sse_line(pending)
                if tail is not None:
                    usage = tail
                if first_token_duration_ms is None and _stream_chunk_has_text(b"", pending + b"\n"):
                    first_token_duration_ms = _duration_ms(started_at_counter)
                completed = True
            finally:
                try:
                    await asyncio.shield(
                        self._finalize(
                            prepared,
                            success=completed,
                            usage=usage,
                            upstream_payload=usage,
                            started_at=started_at,
                            completed_at=datetime.now(UTC),
                            duration_ms=_duration_ms(started_at_counter),
                            first_token_duration_ms=first_token_duration_ms,
                        )
                    )
                except Exception:
                    logger.exception("文本流式结算失败 resource_id=%s", prepared.billing.resource_id)

        return relay()


class GeminiContentApplicationService:
    """按公开模型类型把 Gemini ``:generateContent`` 请求分派到图片或文本用例。

    图像模型与文本模型共用同一个 Gemini 端点，因此先解析平台模型类型，再交给对应用例，使图片按次
    计费、文本按 token 计费，并复用各自的能力校验与结算链路。
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def generate_content(
        self,
        *,
        user_id: UUID,
        group_ids: list[int],
        access_token_id: UUID,
        token_display_name: str | None,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """同步生成内容；图像模型走图片生成用例。"""

        if await self._model_type(payload) == "image":
            return await ImageGenerationApplicationService(self._session_factory).generate_image(
                user_id=user_id,
                group_ids=group_ids,
                access_token_id=access_token_id,
                token_display_name=token_display_name,
                payload=payload,
            )
        return await TextGenerationApplicationService(self._session_factory).chat(
            user_id=user_id,
            group_ids=group_ids,
            access_token_id=access_token_id,
            token_display_name=token_display_name,
            payload=payload,
        )

    async def stream_generate_content(
        self,
        *,
        user_id: UUID,
        group_ids: list[int],
        access_token_id: UUID,
        token_display_name: str | None,
        payload: dict[str, Any],
    ) -> tuple[AsyncIterator[bytes], str]:
        """流式生成内容；Gemini 图像模型不提供流式响应。"""

        if await self._model_type(payload) != "text":
            raise ValidationError("当前模型不支持流式生成")
        return await TextGenerationApplicationService(self._session_factory).chat_stream_native(
            user_id=user_id,
            group_ids=group_ids,
            access_token_id=access_token_id,
            token_display_name=token_display_name,
            payload=payload,
        )

    async def _model_type(self, payload: dict[str, Any]) -> str:
        model_name = payload.get("model")
        if not isinstance(model_name, str) or not model_name:
            raise ValidationError("model 必须是字符串")
        async with self._session_factory() as session:
            model_type = await session.run_sync(_active_model_type, model_name)
        if model_type is None:
            raise ValidationError("未配置当前公开模型")
        return model_type


def _active_model_type(sync_session, model_name: str) -> str | None:
    return ChannelCrud(sync_session).get_active_model_type(name=model_name)


def _ensure_stream_usage(payload: dict[str, Any]) -> dict[str, Any]:
    """后付费流式请求需上游回传用量，缺失时补记 stream_options.include_usage。"""

    if not payload.get("stream"):
        return payload
    normalized = dict(payload)
    options = normalized.get("stream_options")
    if isinstance(options, dict):
        if options.get("include_usage") is True:
            return normalized
        normalized["stream_options"] = {**options, "include_usage": True}
        return normalized
    normalized["stream_options"] = {"include_usage": True}
    return normalized


def _image_pixel_count(size: object) -> int | None:
    if not isinstance(size, str):
        return None
    match = re.fullmatch(r"\s*(\d{1,9})\s*[xX×]\s*(\d{1,9})\s*", size)
    if match is None:
        return None
    width, height = (int(value) for value in match.groups())
    if width <= 0 or height <= 0:
        return None
    return width * height


def _derived_pricing_fields(contract: object) -> list[dict[str, Any]]:
    if not isinstance(contract, dict):
        return []
    declarations = contract.get("derived_pricing_fields")
    return declarations if isinstance(declarations, list) else []


def _reject_client_derived_fields(payload: dict[str, Any], declarations: list[dict[str, Any]]) -> None:
    for declaration in declarations:
        field_name = declaration.get("type") if isinstance(declaration, dict) else None
        if isinstance(field_name, str) and field_name in payload:
            raise ValidationError(
                f"字段 {field_name} 由系统派生，不能提交",
                code="contract.field_derived_by_system",
                params={"name": field_name},
            )


def _provider_request(payload: dict[str, Any], declarations: list[dict[str, Any]]) -> dict[str, Any]:
    derived_fields = {
        declaration["type"]
        for declaration in declarations
        if isinstance(declaration, dict) and isinstance(declaration.get("type"), str)
    }
    return {field: value for field, value in payload.items() if field not in derived_fields}


def _validate_image_uploads(uploads: list[ProviderUpload]) -> None:
    """校验图片编辑输入文件的数量、字段名、类型与大小。"""

    if not uploads:
        raise ValidationError("图片编辑必须提供输入图片")
    image_count = 0
    mask_count = 0
    for upload in uploads:
        if upload.field_name not in _ALLOWED_IMAGE_FIELDS:
            raise ValidationError(
                f"图片编辑不支持字段：{upload.field_name}",
                code="generation.image_edit_unsupported_field",
                params={"name": upload.field_name},
            )
        if upload.field_name == "mask":
            mask_count += 1
        else:
            image_count += 1
        content_type = upload.content_type or ""
        if content_type != "application/octet-stream" and not content_type.startswith("image/"):
            raise ValidationError("图片编辑仅支持图片类型文件")
        if len(upload.content) > _MAX_UPLOAD_BYTES:
            raise ValidationError("图片编辑输入文件超出大小限制")
    if image_count == 0:
        raise ValidationError("图片编辑必须提供输入图片")
    if image_count > _MAX_IMAGE_UPLOADS:
        raise ValidationError("图片编辑输入图片数量超出限制")
    if mask_count > 1:
        raise ValidationError("图片编辑最多提供一个蒙版")


def _normalize_payload(payload: dict[str, Any], input_schema: dict[str, Any]) -> dict[str, Any]:
    """按模型契约对已声明字段做类型归一，未声明字段原样透传以保持兼容。"""

    properties = input_schema.get("properties")
    required = input_schema.get("required") or []
    if not isinstance(properties, dict) or not isinstance(required, list):
        raise ValueError("模型请求契约不合法")
    normalized = {key: value for key, value in payload.items() if value is not None}
    for field, rule in properties.items():
        if field == "model" or field in normalized or not isinstance(rule, dict):
            continue
        if "default" in rule:
            normalized[field] = rule["default"]
    for field in list(normalized):
        if field == "model":
            continue
        rule = properties.get(field)
        if isinstance(rule, dict):
            normalized[field] = _coerce_value(normalized[field], rule.get("type"))
    for field in required:
        if field == "model":
            continue
        if normalized.get(field) in (None, ""):
            raise ValidationError(
                f"缺少模型必填字段：{field}", code="contract.missing_required_fields", params={"name": field}
            )
    for field, rule in properties.items():
        if field in normalized and isinstance(rule, dict):
            _validate_declared_field(field, normalized[field], rule)
    return normalized


def _coerce_value(value: Any, field_type: object) -> Any:
    if not isinstance(field_type, str):
        return value
    if field_type == "array":
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return [value]
            return parsed if isinstance(parsed, list) else [value]
        return value
    if isinstance(value, list):
        return value
    if field_type == "boolean" and isinstance(value, str):
        lowered = value.lower()
        if lowered in {"true", "false"}:
            return lowered == "true"
        return value
    if isinstance(value, str):
        if field_type == "integer":
            try:
                return int(value)
            except ValueError:
                return value
        if field_type == "number":
            try:
                return float(value)
            except ValueError:
                return value
        if field_type == "object":
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
    return value


def _validate_declared_field(field: str, value: Any, rule: dict[str, Any]) -> None:
    """校验已声明字段的基础类型、枚举与边界，不拒绝未声明字段。

    字段规则省略 ``type`` 时表示任意 JSON 类型，不做类型相关校验。
    """

    field_type = rule.get("type")
    if field_type is None:
        return
    if field_type not in _SUPPORTED_FIELD_TYPES:
        raise ValidationError(
            f"模型字段契约不合法：{field}", code="contract.invalid_field_contract", params={"name": field}
        )
    matches = {
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, int | float) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "array": isinstance(value, list),
        "object": isinstance(value, dict),
    }
    if not matches[field_type]:
        raise ValidationError(
            f"字段 {field} 类型必须为 {field_type}",
            code="contract.field_type_mismatch",
            params={"name": field, "expected": field_type},
        )
    if "enum" in rule and value not in rule["enum"]:
        raise ValidationError(f"字段 {field} 不在允许枚举中", code="contract.field_not_in_enum", params={"name": field})
    if field_type == "string":
        if "minLength" in rule and len(value) < rule["minLength"]:
            raise ValidationError(
                f"字段 {field} 长度不足", code="contract.field_length_too_short", params={"name": field}
            )
        if "maxLength" in rule and len(value) > rule["maxLength"]:
            raise ValidationError(
                f"字段 {field} 长度超出限制", code="contract.field_length_too_long", params={"name": field}
            )
    if field_type == "array":
        if "minItems" in rule and len(value) < rule["minItems"]:
            raise ValidationError(f"字段 {field} 项数不足", code="contract.field_items_too_few", params={"name": field})
        if "maxItems" in rule and len(value) > rule["maxItems"]:
            raise ValidationError(
                f"字段 {field} 项数超出限制", code="contract.field_items_too_many", params={"name": field}
            )
    if field_type in {"integer", "number"}:
        if "minimum" in rule and value < rule["minimum"]:
            raise ValidationError(
                f"字段 {field} 小于最小值", code="contract.field_below_minimum", params={"name": field}
            )
        if "maximum" in rule and value > rule["maximum"]:
            raise ValidationError(
                f"字段 {field} 大于最大值", code="contract.field_above_maximum", params={"name": field}
            )


def _group_by_rule(records: list[Any]) -> dict[UUID, list[Any]]:
    grouped: dict[UUID, list[Any]] = defaultdict(list)
    for record in records:
        grouped[record.pricing_rule_id].append(record)
    return grouped


def _duration_ms(started_at_counter: float) -> int:
    return max(int((perf_counter() - started_at_counter) * 1000), 0)


def _has_response_text(payload: dict[str, Any]) -> bool:
    choices = payload.get("choices")
    if isinstance(choices, list) and any(
        isinstance(choice, dict)
        and (
            _has_text_content(choice.get("text"))
            or (isinstance(choice.get("message"), dict) and _has_text_content(choice["message"].get("content")))
        )
        for choice in choices
    ):
        return True
    output = payload.get("output")
    if isinstance(output, list) and any(
        isinstance(item, dict) and _has_text_content(item.get("content")) for item in output
    ):
        return True
    if _has_dashscope_output_text(output):
        return True
    candidates = payload.get("candidates")
    return isinstance(candidates, list) and any(
        isinstance(candidate, dict)
        and isinstance(candidate.get("content"), dict)
        and _has_text_content(candidate["content"].get("parts"))
        for candidate in candidates
    )


def _stream_chunk_has_text(buffer: bytes, chunk: bytes) -> bool:
    lines = (buffer + chunk).split(b"\n")
    for line in lines[:-1]:
        payload = _sse_payload(line)
        if not isinstance(payload, dict):
            continue
        if _has_text_content(payload.get("delta")):
            return True
        if _has_dashscope_output_text(payload.get("output")):
            return True
        candidates = payload.get("candidates")
        if isinstance(candidates, list) and any(
            isinstance(candidate, dict)
            and isinstance(candidate.get("content"), dict)
            and _has_text_content(candidate["content"].get("parts"))
            for candidate in candidates
        ):
            return True
        choices = payload.get("choices")
        if not isinstance(choices, list):
            continue
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            delta = choice.get("delta")
            if isinstance(delta, dict) and _has_text_content(delta.get("content")):
                return True
    return False


def _has_dashscope_output_text(output: Any) -> bool:
    """识别 DashScope Generation 的 ``output`` 文本，兼容文本与多模态两种形状。"""

    if not isinstance(output, dict):
        return False
    if _has_text_content(output.get("text")):
        return True
    choices = output.get("choices")
    if not isinstance(choices, list):
        return False
    for choice in choices:
        if not isinstance(choice, dict):
            continue
        for key in ("message", "delta"):
            block = choice.get(key)
            if isinstance(block, dict) and _has_text_content(block.get("content")):
                return True
    return False


def _has_text_content(content: Any) -> bool:
    if isinstance(content, str):
        return bool(content.strip())
    if isinstance(content, list):
        return any(
            isinstance(item, dict)
            and (item.get("type") in {None, "text", "output_text"})
            and _has_text_content(item.get("text"))
            for item in content
        )
    return False


def _consume_stream_usage(buffer: bytes, chunk: bytes) -> tuple[bytes, dict[str, Any] | None]:
    """按 SSE 事件行增量解析 usage，返回未成行的残片与本批最后一次解析结果。

    HTTP 字节块边界与 SSE 事件边界无关，因此必须保留跨块残片，不能把单个字节块当作完整事件。
    """

    usage: dict[str, Any] | None = None
    lines = (buffer + chunk).split(b"\n")
    remainder = lines.pop()
    if len(remainder) > _MAX_SSE_PENDING_BYTES:
        raise ProviderError("上游流式响应包含超长未完成事件", code="invalid_stream", retryable=False)
    for line in lines:
        found = _usage_from_sse_line(line)
        if found is not None:
            usage = found
    return remainder, usage


def _usage_from_sse_line(line: bytes) -> dict[str, Any] | None:
    """从单条 SSE 数据行中提取 usage 对象，非数据行或非法 JSON 返回 None。"""

    payload = _sse_payload(line)
    if isinstance(payload, dict) and isinstance(payload.get("usage"), dict):
        return payload["usage"]
    response = payload.get("response") if isinstance(payload, dict) else None
    if isinstance(response, dict) and isinstance(response.get("usage"), dict):
        return response["usage"]
    if isinstance(payload, dict) and isinstance(payload.get("usageMetadata"), dict):
        return payload["usageMetadata"]
    return None


def _response_usage(payload: dict[str, Any]) -> dict[str, Any] | None:
    usage = payload.get("usage")
    if isinstance(usage, dict):
        return usage
    usage_metadata = payload.get("usageMetadata")
    return usage_metadata if isinstance(usage_metadata, dict) else None


def _sse_payload(line: bytes) -> dict[str, Any] | None:
    text = line.strip()
    if not text.startswith(b"data:"):
        return None
    data = text[5:].strip()
    if not data or data == b"[DONE]":
        return None
    try:
        payload = json.loads(data.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def summarize_upstream_payload(result: dict[str, Any]) -> dict[str, Any]:
    """生成可安全持久化的上游响应摘要，避免存储内联图片与超长文本。"""

    data = result.get("data")
    if isinstance(data, list):
        return {
            "created": result.get("created"),
            "data": [
                {key: value for key, value in item.items() if key != "b64_json"}
                for item in data
                if isinstance(item, dict)
            ],
        }
    if isinstance(result.get("candidates"), list):
        return {
            "modelVersion": result.get("modelVersion"),
            "usageMetadata": result.get("usageMetadata") if isinstance(result.get("usageMetadata"), dict) else None,
            "candidates": [
                {"content": {"parts": [{"inlineData": {}}]}} for _ in range(_image_output_count({}, result))
            ],
        }
    if "choices" in result or isinstance(result.get("usage"), dict):
        return {
            "id": result.get("id"),
            "model": result.get("model"),
            "usage": result.get("usage") if isinstance(result.get("usage"), dict) else None,
        }
    return {"keys": sorted(str(key) for key in result)}


class ModelCatalogApplicationService:
    """对外模型清单用例，按调用方分组返回可路由的启用模型。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def list_models(self, *, group_ids: list[int]) -> dict[str, Any]:
        """返回 OpenAI 兼容的模型清单，仅包含调用方分组可路由的模型。"""

        async with self._session_factory() as session:
            data = await session.run_sync(_list_routable_models, group_ids)
        return {"object": "list", "data": data}

    async def list_gemini_models(self, *, group_ids: list[int]) -> dict[str, Any]:
        """按 Gemini ListModels 形状返回调用方分组可路由的模型。"""

        async with self._session_factory() as session:
            data = await session.run_sync(_list_routable_model_names, group_ids)
        return {"models": [{"name": name, "displayName": name} for name in data], "nextPageToken": None}


def _list_routable_models(sync_session, group_ids: list[int]) -> list[dict[str, Any]]:
    """把分组可路由模型投影为 OpenAI 模型对象，附带各模型可用的公开调用端点。"""

    models = ChannelCrud(sync_session).list_active_models_for_groups(group_ids=group_ids)
    return [
        {
            "id": model.name,
            "object": "model",
            "created": int(model.created_at.timestamp()) if model.created_at is not None else 0,
            "owned_by": "system",
            "supported_endpoints": model_operations(template_id=model.template_id, model_type=model.model_type),
        }
        for model in models
    ]


def _list_routable_model_names(sync_session, group_ids: list[int]) -> list[str]:
    """把分组可路由模型投影为模型名清单。"""

    return [model.name for model in ChannelCrud(sync_session).list_active_models_for_groups(group_ids=group_ids)]
