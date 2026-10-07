"""模型渠道路由快照及 Redis 跨进程失效广播。"""

import json
import logging
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal
from threading import Event, Lock
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy.orm import Session

from app.infrastructure.redis.client import get_redis_client, routing_snapshot_circuit_breaker
from app.modules.channels.application.routing import RoutableChannelBinding

logger = logging.getLogger(__name__)

_INVALIDATION_CHANNEL = "routing-snapshot:invalidate"
_INVALIDATION_MESSAGE = {"scope": "all"}


@dataclass(frozen=True, slots=True)
class RoutingBindingSnapshot:
    id: UUID
    priority: int
    weight: int
    enabled: bool
    healthy: bool
    token_group_id: int


@dataclass(frozen=True, slots=True)
class RoutingChannelSnapshot:
    id: UUID
    name: str
    active: bool
    healthy: bool
    base_url: str
    config: dict[str, object]
    model_mapping: dict[str, str]
    param_override: dict[str, object]
    api_key: str


@dataclass(frozen=True, slots=True)
class GenerationModelSnapshot:
    id: UUID
    name: str
    model_type: str
    template_id: str | None
    input_contract: dict[str, Any] | None
    pricing_fields: list[str]
    active: bool


@dataclass(frozen=True, slots=True)
class PricingRuleSnapshot:
    id: UUID
    model_id: UUID
    token_group_id: int
    name: str
    priority: int
    conditions: list[dict[str, Any]]
    currency: str
    active: bool


@dataclass(frozen=True, slots=True)
class PricingItemSnapshot:
    id: UUID
    pricing_rule_id: UUID
    label: str
    position: int
    kind: str
    source_fields: list[str]
    free_quantity: int
    unit_amount: Decimal | None
    price_source_item_id: UUID | None
    active: bool


@dataclass(frozen=True, slots=True)
class PricingModifierSnapshot:
    id: UUID
    pricing_rule_id: UUID
    name: str
    priority: int
    conditions: list[dict[str, Any]]
    effect_type: str
    effect_payload: dict[str, Any]
    scope_type: str
    scope_item_ids: list[str]
    scope_item_kinds: list[str]
    active: bool


@dataclass(frozen=True, slots=True)
class GenerationConfigurationSnapshot:
    model: GenerationModelSnapshot
    channels: tuple[RoutableChannelBinding, ...]
    rules: tuple[PricingRuleSnapshot, ...]
    items: tuple[PricingItemSnapshot, ...]
    modifiers: tuple[PricingModifierSnapshot, ...]


class RoutingSnapshotStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self._snapshots: dict[tuple[UUID, tuple[int, ...]], tuple[RoutableChannelBinding, ...]] = {}
        self._loading: dict[tuple[UUID, tuple[int, ...]], Event] = {}
        self._generation = 0

    def get_or_load(
        self,
        *,
        model_id: UUID,
        group_ids: list[int],
        loader: Callable[[], list[RoutableChannelBinding]],
    ) -> list[RoutableChannelBinding]:
        key = model_id, tuple(group_ids)
        while True:
            with self._lock:
                snapshot = self._snapshots.get(key)
                if snapshot is not None:
                    return list(snapshot)
                loading = self._loading.get(key)
                if loading is None:
                    loading = Event()
                    self._loading[key] = loading
                    generation = self._generation
                    is_loader = True
                else:
                    is_loader = False
            if not is_loader:
                loading.wait()
                continue
            try:
                loaded = tuple(loader())
            except Exception:
                with self._lock:
                    if self._loading.get(key) is loading:
                        self._loading.pop(key)
                        loading.set()
                raise
            with self._lock:
                if self._generation == generation:
                    self._snapshots[key] = loaded
                    self._loading.pop(key)
                    loading.set()
                    return list(loaded)
                if self._loading.get(key) is loading:
                    self._loading.pop(key)
                    loading.set()

    def invalidate(self) -> None:
        with self._lock:
            self._snapshots.clear()
            self._generation += 1


routing_snapshot_store = RoutingSnapshotStore()


def list_routable_channel_bindings(
    session: Session,
    *,
    model_id: UUID,
    group_ids: list[int],
    loader: Callable[[], list[tuple[object, object]]],
) -> list[RoutableChannelBinding]:
    return routing_snapshot_store.get_or_load(
        model_id=model_id,
        group_ids=group_ids,
        loader=lambda: _freeze_routing_snapshot(loader()),
    )


def get_generation_configuration_snapshot(
    *,
    model_name: str,
    model_type: str,
    group_ids: list[int],
    loader: Callable[
        [], tuple[object | None, list[tuple[object, object]], tuple[list[object], list[object], list[object]]]
    ],
) -> GenerationConfigurationSnapshot | None:
    snapshot = routing_snapshot_store.get_or_load(
        model_id=_generation_snapshot_key(model_name, model_type),
        group_ids=group_ids,
        loader=lambda: [_freeze_generation_configuration(loader())],
    )
    return snapshot[0] if snapshot else None


def publish_routing_snapshot_invalidation() -> None:
    routing_snapshot_store.invalidate()
    try:
        routing_snapshot_circuit_breaker.execute(
            lambda: get_redis_client().publish(_INVALIDATION_CHANNEL, json.dumps(_INVALIDATION_MESSAGE))
        )
    except Exception:
        logger.warning("路由快照 Redis 失效广播失败，本进程已清除快照", exc_info=True)


def process_routing_snapshot_invalidation(message: str) -> bool:
    try:
        payload = json.loads(message)
    except (TypeError, json.JSONDecodeError):
        return False
    if payload != _INVALIDATION_MESSAGE:
        return False
    routing_snapshot_store.invalidate()
    return True


class RoutingSnapshotInvalidationSubscriber:
    def __init__(self, *, redis_client_factory: Callable = get_redis_client) -> None:
        self._redis_client_factory = redis_client_factory
        self._pubsub = None

    def listen_once(self) -> None:
        if self._pubsub is None:
            self._pubsub = self._redis_client_factory().pubsub(ignore_subscribe_messages=True)
            self._pubsub.subscribe(_INVALIDATION_CHANNEL)
        message = self._pubsub.get_message(timeout=1.0)
        if not isinstance(message, dict) or message.get("type") != "message":
            return
        data = message.get("data")
        if isinstance(data, str):
            process_routing_snapshot_invalidation(data)

    def close(self) -> None:
        if self._pubsub is not None:
            self._pubsub.close()
            self._pubsub = None


def _freeze_routing_snapshot(rows: list[tuple[object, object]]) -> list[RoutableChannelBinding]:
    return [
        RoutableChannelBinding(
            binding=RoutingBindingSnapshot(
                id=binding.id,
                priority=binding.priority,
                weight=binding.weight,
                enabled=binding.enabled,
                healthy=binding.healthy,
                token_group_id=binding.token_group_id,
            ),
            channel=RoutingChannelSnapshot(
                id=channel.id,
                name=getattr(channel, "name", ""),
                active=channel.active,
                healthy=channel.healthy,
                base_url=channel.base_url,
                config=dict(channel.config),
                model_mapping=dict(channel.model_mapping),
                param_override=dict(channel.param_override),
                api_key=channel.api_key,
            ),
        )
        for binding, channel in rows
    ]


def _generation_snapshot_key(model_name: str, model_type: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"generation-configuration:{model_type}:{model_name}")


def _freeze_generation_configuration(
    loaded: tuple[object | None, list[tuple[object, object]], tuple[list[object], list[object], list[object]]],
) -> GenerationConfigurationSnapshot | None:
    model, rows, pricing = loaded
    if model is None:
        return None
    rules, items, modifiers = pricing
    return GenerationConfigurationSnapshot(
        model=GenerationModelSnapshot(
            id=model.id,
            name=model.name,
            model_type=model.model_type,
            template_id=getattr(model, "template_id", None),
            input_contract=deepcopy(model.input_contract),
            pricing_fields=list(model.pricing_fields),
            active=getattr(model, "active", True),
        ),
        channels=tuple(_freeze_routing_snapshot(rows)),
        rules=tuple(
            PricingRuleSnapshot(
                id=rule.id,
                model_id=rule.model_id,
                token_group_id=rule.token_group_id,
                name=rule.name,
                priority=rule.priority,
                conditions=deepcopy(rule.conditions),
                currency=rule.currency,
                active=rule.active,
            )
            for rule in rules
        ),
        items=tuple(
            PricingItemSnapshot(
                id=item.id,
                pricing_rule_id=item.pricing_rule_id,
                label=item.label,
                position=item.position,
                kind=item.kind,
                source_fields=list(item.source_fields),
                free_quantity=item.free_quantity,
                unit_amount=item.unit_amount,
                price_source_item_id=item.price_source_item_id,
                active=item.active,
            )
            for item in items
        ),
        modifiers=tuple(
            PricingModifierSnapshot(
                id=modifier.id,
                pricing_rule_id=modifier.pricing_rule_id,
                name=modifier.name,
                priority=modifier.priority,
                conditions=deepcopy(modifier.conditions),
                effect_type=modifier.effect_type,
                effect_payload=deepcopy(modifier.effect_payload),
                scope_type=modifier.scope_type,
                scope_item_ids=list(modifier.scope_item_ids),
                scope_item_kinds=list(modifier.scope_item_kinds),
                active=modifier.active,
            )
            for modifier in modifiers
        ),
    )
