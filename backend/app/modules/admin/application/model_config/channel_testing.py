import time
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.bootstrap.container import get_channel_provider_factory, get_provider_template_registry
from app.core.config import get_settings
from app.core.errors import NotFoundError, ValidationError
from app.modules.admin.crud.channel_crud import ChannelCrud as AdminChannelCrud
from app.modules.admin.crud.model_crud import ModelCrud
from app.modules.channels.application.model_mapping import apply_upstream_model_name
from app.modules.channels.crud.channels import ChannelCrud as ConfigurationChannelCrud
from app.modules.models.model import Model
from app.modules.pricing.application.engine import MaterialFacts, list_unpriced_groups, quote_pricing
from app.modules.providers.contracts import GenerationProvider, ProviderError
from app.modules.usage.application.normalization import normalize_text_usage
from app.modules.usage.application.services import UsageApplicationService
from app.modules.user.crud.token_group_crud import TokenGroupCrud

_TEST_CHAT_MESSAGE = "hi"
_TEST_CHAT_MAX_TOKENS = 16
_TEST_IMAGE_PROMPT = "a cute cat"
_TEST_IMAGE_SIZE = "1024x1024"
_TESTABLE_MODEL_TYPES = {"text", "image"}


@dataclass(frozen=True)
class _TestTarget:
    channel_id: UUID
    channel_name: str
    model_id: UUID
    model_name: str
    model_type: str
    provider_name: str
    provider: GenerationProvider
    request_body: dict[str, Any]
    pricing_rules: list[Any]
    pricing_items: list[Any]
    pricing_modifiers: list[Any]
    pricing_fields: list[str]
    group_ids: list[int]
    group_multipliers: dict[int, Decimal]


class ChannelTestApplicationService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def test_channel(self, *, admin_user_id: UUID, channel_id: UUID, model: str | None = None) -> dict[str, Any]:
        async with self._session_factory() as session:
            target = await session.run_sync(_build_test_target, channel_id, model)
        started_at = time.perf_counter()
        try:
            response = await _call_provider(target.provider, target.model_type, target.request_body)
            result, usage = _extract_result(target.model_type, response)
        except ProviderError as exc:
            return await self._finalize(
                admin_user_id=admin_user_id,
                target=target,
                started_at=started_at,
                succeeded=False,
                amount=Decimal(0),
                usage={},
                error_code=exc.code,
                message=_safe_error_message(exc),
                pricing_snapshot=None,
                result=None,
            )
        except (ValueError, TypeError):
            return await self._finalize(
                admin_user_id=admin_user_id,
                target=target,
                started_at=started_at,
                succeeded=False,
                amount=Decimal(0),
                usage={},
                error_code="invalid_response",
                message="上游返回无有效计费数据" if target.model_type == "text" else "上游返回无有效结果",
                pricing_snapshot=None,
                result=None,
            )
        try:
            amount, pricing_snapshot = _quote_target(target, usage)
        except (ValueError, TypeError):
            return await self._finalize(
                admin_user_id=admin_user_id,
                target=target,
                started_at=started_at,
                succeeded=True,
                amount=Decimal(0),
                usage=usage,
                error_code="pricing_unavailable",
                message="上游调用成功，但无可用计费配置",
                pricing_snapshot=None,
                result=result,
            )
        return await self._finalize(
            admin_user_id=admin_user_id,
            target=target,
            started_at=started_at,
            succeeded=True,
            amount=amount,
            usage=usage,
            error_code=None,
            message="",
            pricing_snapshot=pricing_snapshot,
            result=result,
        )

    async def _finalize(
        self,
        *,
        admin_user_id: UUID,
        target: _TestTarget,
        started_at: float,
        succeeded: bool,
        amount: Decimal,
        usage: dict[str, int | str],
        error_code: str | None,
        message: str,
        pricing_snapshot: dict[str, object] | None,
        result: dict[str, Any] | None,
    ) -> dict[str, Any]:
        duration_ms = max(0, round((time.perf_counter() - started_at) * 1000))
        async with self._session_factory() as session:
            await session.run_sync(
                _persist_test_result,
                admin_user_id,
                target,
                duration_ms,
                succeeded,
                amount,
                usage,
                error_code,
                message,
                pricing_snapshot,
            )
        return {
            "success": succeeded,
            "message": message,
            "time": round(duration_ms / 1000, 3),
            "amount": amount,
            "result": result,
        }


def _build_test_target(sync_session, channel_id: UUID, model_name: str | None) -> _TestTarget:
    channel = AdminChannelCrud(sync_session).get(channel_id)
    if channel is None:
        raise NotFoundError("渠道不存在")
    if not channel.active:
        raise ValidationError("渠道已停用，无法测试")
    model = _resolve_test_model(sync_session, channel.supported_models, model_name)
    template = get_provider_template_registry().get(model.template_id)
    if template is None:
        raise ValidationError("模型模板不存在")
    rules, items, modifiers = ConfigurationChannelCrud(sync_session).list_pricing_configuration(model_id=model.id)
    unpriced_group_ids = list_unpriced_groups(rules, group_ids=channel.token_group_ids)
    if unpriced_group_ids:
        raise ValidationError(
            _missing_pricing_message(channel_name=channel.name, model_name=model.name, group_ids=unpriced_group_ids)
        )
    groups = TokenGroupCrud(sync_session).list_groups_by_ids(set(channel.token_group_ids))
    group_multipliers = {group.id: group.price_multiplier for group in groups}
    request_body = _build_test_request(model.model_type, model.name)
    apply_upstream_model_name(request_body, channel.model_mapping.get(model.name))
    request_body.update(deepcopy(channel.param_override))
    provider = get_channel_provider_factory().get_frozen_generation_provider(
        {"route_id": str(channel.id), "base_url": channel.base_url, "config": dict(channel.config)},
        provider_type=template["provider_type"],
        api_key=channel.api_key,
    )
    return _TestTarget(
        channel_id=channel.id,
        channel_name=channel.name,
        model_id=model.id,
        model_name=model.name,
        model_type=model.model_type,
        provider_name=template["provider_type"],
        provider=provider,
        request_body=request_body,
        pricing_rules=rules,
        pricing_items=items,
        pricing_modifiers=modifiers,
        pricing_fields=list(model.pricing_fields),
        group_ids=list(channel.token_group_ids),
        group_multipliers=group_multipliers,
    )


def _missing_pricing_message(*, channel_name: str, model_name: str, group_ids: list[int]) -> str:
    """构造渠道测试缺少定价规则的报错文案，指明具体渠道、模型与令牌分组。"""

    groups = "、".join(f"“{group_id}”" for group_id in group_ids)
    return f"渠道“{channel_name}”的模型“{model_name}”在令牌分组{groups}没有启用的定价规则"


def _persist_test_result(
    sync_session,
    admin_user_id: UUID,
    target: _TestTarget,
    duration_ms: int,
    succeeded: bool,
    amount: Decimal,
    usage: dict[str, int | str],
    error_code: str | None,
    message: str,
    pricing_snapshot: dict[str, object] | None,
) -> None:
    try:
        response_metadata: dict[str, object] = {"response_type": target.model_type, **usage}
        if error_code is not None:
            response_metadata["diagnostic"] = {"error_code": error_code, "message": message}
        if pricing_snapshot is not None:
            response_metadata["pricing"] = pricing_snapshot
        UsageApplicationService(sync_session).create_channel_test_result(
            user_id=admin_user_id,
            request_id=str(uuid4()),
            model_id=target.model_id,
            model_name=target.model_name,
            channel_id=target.channel_id,
            channel_name=target.channel_name,
            provider_name=target.provider_name,
            request_payload=_safe_request_payload(target.request_body),
            response_metadata=response_metadata,
            amount=amount if succeeded else Decimal(0),
            duration_ms=duration_ms,
            succeeded=succeeded,
            prompt_tokens=_usage_token(usage, "prompt_tokens"),
            completion_tokens=_usage_token(usage, "completion_tokens"),
            cached_tokens=_usage_token(usage, "cached_tokens"),
            cache_write_tokens=_usage_token(usage, "cache_write_tokens"),
        )
        snapshot: dict[str, object] = {
            "tested_at": datetime.now(UTC).isoformat(),
            "status": "succeeded" if succeeded else "failed",
            "model": target.model_name,
            "model_type": target.model_type,
            "duration_ms": duration_ms,
            "amount": str(amount if succeeded else Decimal(0)),
            "usage": dict(usage),
        }
        if error_code is not None:
            snapshot.update({"error_code": error_code, "message": message})
        AdminChannelCrud(sync_session).update_latest_test_snapshot(channel_id=target.channel_id, snapshot=snapshot)
        sync_session.commit()
    except Exception:
        sync_session.rollback()
        raise


def _resolve_test_model(sync_session, supported_models: list[str], model_name: str | None) -> Model:
    name = (model_name or "").strip()
    if not name:
        if not supported_models:
            raise ValidationError("渠道未配置可测试模型")
        name = supported_models[0]
    if name not in supported_models:
        raise ValidationError("该渠道未配置此模型")
    model = ModelCrud(sync_session).get_by_name(name)
    if model is None or not model.active:
        raise ValidationError("公开模型不存在或未启用")
    if model.model_type not in _TESTABLE_MODEL_TYPES:
        raise ValidationError("该模型类型暂不支持同步测试")
    return model


def _build_test_request(model_type: str, model_name: str) -> dict[str, Any]:
    if model_type == "image":
        return {"model": model_name, "prompt": _TEST_IMAGE_PROMPT, "n": 1, "size": _TEST_IMAGE_SIZE}
    return {
        "model": model_name,
        "messages": [{"role": "user", "content": _TEST_CHAT_MESSAGE}],
        "max_tokens": _TEST_CHAT_MAX_TOKENS,
    }


async def _call_provider(provider: GenerationProvider, model_type: str, request_body: dict[str, Any]) -> dict[str, Any]:
    if model_type == "image":
        generate_image = getattr(provider, "generate_image", None)
        if not callable(generate_image):
            raise ProviderError("当前渠道适配器不支持图片生成测试", code="unsupported_capability", retryable=False)
        return await generate_image(request_body, timeout=get_settings().provider_read_timeout_seconds)
    chat = getattr(provider, "chat", None)
    if not callable(chat):
        raise ProviderError("当前渠道适配器不支持文本生成测试", code="unsupported_capability", retryable=False)
    return await chat(request_body, timeout=get_settings().provider_read_timeout_seconds)


def _extract_result(model_type: str, response: dict[str, Any]) -> tuple[dict[str, Any], dict[str, int | str]]:
    if model_type == "image":
        items = [
            {key: item[key] for key in ("url", "b64_json") if isinstance(item.get(key), str)}
            for item in response.get("data", [])
            if isinstance(item, dict) and any(isinstance(item.get(key), str) for key in ("url", "b64_json"))
        ]
        if not items:
            raise ValueError("图片响应为空")
        return {"type": "image", "items": items}, {"image_count": len(items), "size": _TEST_IMAGE_SIZE}
    content = _extract_text_content(response)
    if not content:
        raise ValueError("文本响应为空")
    normalized_usage = normalize_text_usage(response)
    if normalized_usage is None:
        raise ValueError("缺少用量")
    return {"type": "text", "content": content}, {
        "prompt_tokens": normalized_usage.prompt_tokens,
        "completion_tokens": normalized_usage.completion_tokens,
        "cached_tokens": normalized_usage.cached_tokens,
        "cache_write_tokens": normalized_usage.cache_write_tokens,
    }


def _extract_text_content(response: dict[str, Any]) -> str:
    """提取首个非空文本，兼容 OpenAI、Anthropic、Gemini、DashScope 与 Responses 原生结构。"""

    candidates = _choice_message_contents(response.get("choices"))
    candidates.append(response.get("content"))
    candidates.extend(_candidate_part_contents(response.get("candidates")))
    output = response.get("output")
    if isinstance(output, dict):
        candidates.append(output.get("text"))
        candidates.extend(_choice_message_contents(output.get("choices")))
    elif isinstance(output, list):
        candidates.extend(item.get("content") for item in output if isinstance(item, dict))
    for candidate in candidates:
        text = _text_from_content(candidate)
        if text:
            return text
    return ""


def _choice_message_contents(choices: Any) -> list[Any]:
    if not isinstance(choices, list):
        return []
    return [
        choice["message"]["content"]
        for choice in choices
        if isinstance(choice, dict) and isinstance(choice.get("message"), dict)
    ]


def _candidate_part_contents(candidates: Any) -> list[Any]:
    if not isinstance(candidates, list):
        return []
    parts = []
    for candidate in candidates:
        block = candidate.get("content") if isinstance(candidate, dict) else None
        if isinstance(block, dict) and isinstance(block.get("parts"), list):
            parts.append(block["parts"])
    return parts


def _text_from_content(content: Any) -> str:
    """把字符串或内容块列表折叠为纯文本，忽略非文本块。"""

    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    blocks = [
        block["text"]
        for block in content
        if isinstance(block, dict)
        and block.get("type") in {None, "text", "output_text"}
        and isinstance(block.get("text"), str)
    ]
    return "\n".join(text.strip() for text in blocks if text.strip()).strip()


def _quote_target(target: _TestTarget, usage: dict[str, int | str]) -> tuple[Decimal, dict[str, object]]:
    decision = quote_pricing(
        target.pricing_rules,
        _group_by_rule(target.pricing_items),
        _group_by_rule(target.pricing_modifiers),
        context={**target.request_body, **usage},
        facts=MaterialFacts(),
        allowed_fields=target.pricing_fields,
        group_ids=target.group_ids,
        created_at=datetime.now(UTC),
        group_multipliers=target.group_multipliers,
    )
    return decision.amount, decision.snapshot


def _group_by_rule(records: list[Any]) -> dict[UUID, list[Any]]:
    grouped: dict[UUID, list[Any]] = {}
    for record in records:
        grouped.setdefault(record.pricing_rule_id, []).append(record)
    return grouped


def _usage_token(usage: dict[str, int | str], key: str) -> int | None:
    """从归一化用量中取出计费 token 字段，图片等无该字段时返回 None。"""

    value = usage.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _safe_request_payload(request_body: dict[str, Any]) -> dict[str, object]:
    payload: dict[str, object] = {"model": str(request_body.get("model", ""))}
    if "messages" in request_body:
        payload.update({"type": "text", "max_tokens": int(request_body.get("max_tokens", 0))})
    else:
        payload.update({"type": "image", "n": int(request_body.get("n", 0)), "size": str(request_body.get("size", ""))})
    return payload


def _safe_error_message(error: ProviderError) -> str:
    if error.code == "timeout":
        return "请求超时"
    if error.code in {"network", "upstream_unavailable"}:
        return "上游服务不可用"
    if error.code == "unsupported_capability":
        return "当前渠道适配器不支持该模型测试"
    return str(error)
