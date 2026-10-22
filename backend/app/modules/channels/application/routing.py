"""模型渠道优先级分组、AIMD 权重与运行时选路服务。

本模块只负责选路决策：静态准入过滤、优先级分层、SWRR 参考实现以及 AIMD 权重数学计算。
Redis 状态的读写由 ``channels.runtime.channel_runtime`` 注入实现，本模块不直接访问 Redis。
"""

import logging
import random
from collections import defaultdict
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.modules.channels.model.channel import Channel
from app.modules.models.model import ModelRoute

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RoutableChannelBinding:
    """渠道绑定与渠道实体的可路由组合。"""

    binding: ModelRoute
    channel: Channel


@dataclass(frozen=True)
class ChannelRoute:
    """保存渠道选路的候选快照和最终选中渠道。"""

    binding: ModelRoute
    channel: Channel
    candidates: list[dict[str, object]]


@dataclass(frozen=True, slots=True)
class RuntimeCandidate:
    """参与运行时选路的单个候选渠道信息。"""

    route_id: UUID
    channel_id: UUID
    priority: int
    base_weight: int


@dataclass(frozen=True, slots=True)
class WeightSnapshot:
    """单个路由当前的运行时质量状态。"""

    weight: float
    success_rate: float
    latency_ms: float
    failures: int


@dataclass(frozen=True, slots=True)
class AimdConfig:
    """AIMD 权重计算参数，与 Redis Lua 脚本保持同一套公式。"""

    min_weight: float
    success_increment_ratio: float
    decay_at_min: float
    decay_at_high: float
    high_weight_multiplier: float
    ewma_half_life_samples: int
    latency_baseline_ms: float

    @property
    def ewma_alpha(self) -> float:
        """返回与半衰期样本数对应的 EWMA 平滑系数。"""

        return 1.0 - 0.5 ** (1.0 / self.ewma_half_life_samples)


class ChannelSelectionRuntime(Protocol):
    """运行时选路依赖的最小接口，供 Redis 实现与测试替身实现。"""

    def select(self, candidates: Sequence[RuntimeCandidate]) -> UUID | None:
        """在候选中按动态熔断状态与 SWRR 选出唯一路由；全部不可用时返回 ``None``。"""


def select_channel(
    channels: Iterable[RoutableChannelBinding],
    *,
    random_value: Callable[[], float] = random.random,
) -> ChannelRoute:
    """按优先级组和正整数权重选择唯一可用渠道。

    参数 ``channels`` 为同一模型的已发布绑定，``random_value`` 返回半开区间 [0, 1) 的随机值以支持确定性测试。
    返回选中渠道和参与决策的候选快照；没有启用且健康的候选或随机值越界时抛出 ``ValueError``。
    """

    eligible = [item for item in channels if _is_eligible(item)]
    if not eligible:
        raise ValueError("当前模型没有可用渠道")
    return _select_from_eligible(eligible, random_value=random_value)


def select_channel_in_group_order(
    channels: Iterable[RoutableChannelBinding],
    *,
    group_ids: Iterable[int],
    runtime: ChannelSelectionRuntime | None = None,
    random_value: Callable[[], float] = random.random,
) -> Iterator[ChannelRoute]:
    """按 Token 分组顺序逐个产出该分组内的可用渠道决策。

    参数 ``channels`` 为同一模型在全部可访问分组下的已发布绑定，``group_ids`` 为按绑定优先级排序的分组标识；
    每个分组只使用自身候选项独立选路，不与其他分组的渠道混合，因此返回结果中的候选快照始终属于同一个分组。
    当前分组没有启用且健康的渠道时不产出结果，由调用方决定是否继续尝试下一个兜底分组。

    ``runtime`` 提供 Redis 侧的熔断过滤与 SWRR；运行时不可用时降级为按快照权重的一次性加权随机。
    """

    grouped: dict[int, list[RoutableChannelBinding]] = defaultdict(list)
    for item in channels:
        grouped[item.binding.token_group_id].append(item)
    for group_id in group_ids:
        eligible = [item for item in grouped.get(group_id, []) if _is_eligible(item)]
        if not eligible:
            continue
        if runtime is None:
            yield _select_from_eligible(eligible, random_value=random_value)
            continue
        try:
            selected_id = runtime.select(_runtime_candidates(eligible))
        except Exception:
            logger.warning("渠道运行时选路失败，降级为静态权重随机", exc_info=True)
            yield _select_from_eligible(eligible, random_value=random_value)
            continue
        if selected_id is None:
            continue
        selected = next((item for item in eligible if item.binding.id == selected_id), None)
        if selected is None:
            yield _select_from_eligible(eligible, random_value=random_value)
            continue
        yield ChannelRoute(
            binding=selected.binding,
            channel=selected.channel,
            candidates=[_candidate_snapshot(item) for item in eligible],
        )


def initial_weight_state(base_weight: int, config: AimdConfig) -> WeightSnapshot:
    """构造某个路由的初始运行时状态：权重为初始权重，质量指标为乐观初值。"""

    return WeightSnapshot(
        weight=max(float(base_weight), config.min_weight),
        success_rate=1.0,
        latency_ms=config.latency_baseline_ms,
        failures=0,
    )


def apply_success(
    state: WeightSnapshot,
    *,
    base_weight: int,
    latency_ms: float,
    config: AimdConfig,
    half_open: bool = False,
) -> WeightSnapshot:
    """按成功样本推进 AIMD 状态，返回新的不可变快照。"""

    alpha = config.ewma_alpha
    success_rate = state.success_rate + alpha * (1.0 - state.success_rate)
    latency = state.latency_ms + alpha * (max(latency_ms, 0.0) - state.latency_ms)
    increment = max(1.0, base_weight * config.success_increment_ratio)
    if half_open:
        weight = state.weight + increment
    else:
        speed = _clamp(config.latency_baseline_ms / max(latency, 1.0), 0.25, 2.0)
        low_bonus = 1.0 + 2.0 * _clamp((4.0 * config.min_weight - state.weight) / (3.0 * config.min_weight), 0.0, 1.0)
        weight = state.weight + increment * success_rate * speed * low_bonus
    return WeightSnapshot(
        weight=max(weight, config.min_weight),
        success_rate=success_rate,
        latency_ms=latency,
        failures=0,
    )


def apply_failure(
    state: WeightSnapshot,
    *,
    base_weight: int,
    config: AimdConfig,
) -> WeightSnapshot:
    """按失败样本推进 AIMD 状态：权重越高衰减越强，且永不低于下限。"""

    alpha = config.ewma_alpha
    high_reference = max(float(base_weight) * config.high_weight_multiplier, config.min_weight)
    progress = _clamp((state.weight - config.min_weight) / max(high_reference - config.min_weight, 1e-9), 0.0, 1.0)
    decay = config.decay_at_min - (config.decay_at_min - config.decay_at_high) * progress
    return WeightSnapshot(
        weight=max(state.weight * decay, config.min_weight),
        success_rate=state.success_rate + alpha * (0.0 - state.success_rate),
        latency_ms=state.latency_ms,
        failures=state.failures + 1,
    )


def smooth_weighted_pick(weights: Sequence[float], currents: Sequence[float]) -> tuple[int, list[float]]:
    """按 Nginx SWRR 计算一次选择结果与更新后的当前权重。

    返回选中下标和全部候选项的新当前权重；``weights`` 与 ``currents`` 必须等长且权重为正。
    """

    if len(weights) != len(currents):
        raise ValueError("权重与当前权重数量不一致")
    if not weights:
        raise ValueError("没有可参与轮询的候选")
    updated = [currents[index] + weights[index] for index in range(len(weights))]
    pick = 0
    for index in range(1, len(updated)):
        if updated[index] > updated[pick]:
            pick = index
    total = sum(weights)
    if total <= 0:
        raise ValueError("渠道权重必须为正整数")
    updated[pick] -= total
    return pick, updated


def _is_eligible(item: RoutableChannelBinding) -> bool:
    """判断绑定与渠道是否同时启用且健康，作为选路的唯一静态准入条件。"""

    return bool(
        item.binding.enabled and item.binding.healthy and item.channel.active and getattr(item.channel, "healthy", True)
    )


def _runtime_candidates(eligible: list[RoutableChannelBinding]) -> list[RuntimeCandidate]:
    return [
        RuntimeCandidate(
            route_id=item.binding.id,
            channel_id=item.channel.id,
            priority=item.binding.priority,
            base_weight=item.binding.weight,
        )
        for item in eligible
    ]


def _select_from_eligible(
    eligible: list[RoutableChannelBinding],
    *,
    random_value: Callable[[], float],
) -> ChannelRoute:
    """在已过滤的候选集合内按最小优先级组和权重随机选出唯一渠道。"""

    priority = min(item.binding.priority for item in eligible)
    group = [item for item in eligible if item.binding.priority == priority]
    candidates = [_candidate_snapshot(item) for item in group]
    total_weight = sum(item.binding.weight for item in group)
    if total_weight <= 0:
        raise ValueError("渠道权重必须为正整数")
    value = random_value()
    if not 0 <= value < 1:
        raise ValueError("渠道随机源必须返回大于等于零且小于一的数值")
    threshold = value * total_weight
    accumulated = 0
    for item in group:
        accumulated += item.binding.weight
        if threshold < accumulated:
            return ChannelRoute(binding=item.binding, channel=item.channel, candidates=candidates)
    return ChannelRoute(binding=group[-1].binding, channel=group[-1].channel, candidates=candidates)


def _candidate_snapshot(item: RoutableChannelBinding) -> dict[str, object]:
    """生成供任务执行的脱敏渠道冻结候选项。"""

    return {
        "channel_id": str(item.channel.id),
        "route_id": str(item.binding.id),
        "priority": item.binding.priority,
        "weight": item.binding.weight,
        "base_url": item.channel.base_url,
        "config": dict(item.channel.config),
    }


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))
