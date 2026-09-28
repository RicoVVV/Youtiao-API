"""模型渠道优先级分组与同级加权选路服务。

本模块只根据已发布渠道配置产生可冻结的选择结果，不读取 Provider 状态、不调用上游服务，也不修改数据库。
调用方负责将结果连同候选集写入任务和报价快照。
"""

import random
from collections import defaultdict
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass

from app.modules.channels.model.channel import Channel
from app.modules.models.model import ModelRoute


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
    random_value: Callable[[], float] = random.random,
) -> Iterator[ChannelRoute]:
    """按 Token 分组顺序逐个产出该分组内的可用渠道决策。

    参数 ``channels`` 为同一模型在全部可访问分组下的已发布绑定，``group_ids`` 为按绑定优先级排序的分组标识；
    每个分组只使用自身候选项独立选路，不与其他分组的渠道混合，因此返回结果中的候选快照始终属于同一个分组。
    当前分组没有启用且健康的渠道时不产出结果，由调用方决定是否继续尝试下一个兜底分组。
    """

    grouped: dict[int, list[RoutableChannelBinding]] = defaultdict(list)
    for item in channels:
        grouped[item.binding.token_group_id].append(item)
    for group_id in group_ids:
        eligible = [item for item in grouped.get(group_id, []) if _is_eligible(item)]
        if not eligible:
            continue
        yield _select_from_eligible(eligible, random_value=random_value)


def _is_eligible(item: RoutableChannelBinding) -> bool:
    """判断绑定与渠道是否同时启用且健康，作为选路的唯一准入条件。"""

    return bool(
        item.binding.enabled and item.binding.healthy and item.channel.active and getattr(item.channel, "healthy", True)
    )


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
