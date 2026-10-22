"""渠道运行时状态：SWRR 选路、AIMD 权重反馈、熔断与探测状态。

状态按 route 与 channel 两个维度存放在 Redis：
- ``routing:route:{route_id}``：有效权重、SWRR 当前权重、成功率与耗时 EWMA、连续失败数；
- ``routing:channel:{channel_id}``：熔断状态、冷却截止时间、半开租约与探测计数。

选路与反馈都通过 Lua 脚本原子执行，保证多 worker 之间共享同一份调度状态。所有异常由调用方决定降级方式。
"""

import logging
from dataclasses import dataclass
from functools import lru_cache
from time import time
from uuid import UUID

from redis import Redis

from app.core.config import Settings, get_settings
from app.infrastructure.redis.client import get_redis_client
from app.modules.channels.application.routing import AimdConfig, RuntimeCandidate

logger = logging.getLogger(__name__)

_ROUTE_KEY = "routing:route:{}"
_CHANNEL_KEY = "routing:channel:{}"

_SELECT_SCRIPT = """
local n = math.floor(#KEYS / 2)
local now = tonumber(ARGV[1])
local lease = tonumber(ARGV[2])
local min_w = tonumber(ARGV[3])
local ttl = tonumber(ARGV[4])

local best_priority = nil
local available = {}
for i = 1, n do
  local channel_key = KEYS[n + i]
  local state = redis.call('HGET', channel_key, 'state')
  local ok = true
  if state == 'open' then
    local open_until = tonumber(redis.call('HGET', channel_key, 'open_until') or '0')
    if now >= open_until then
      redis.call('HSET', channel_key, 'state', 'half_open')
      redis.call('HSET', channel_key, 'probe_lease_until', tostring(now + lease))
    else
      ok = false
    end
  elseif state == 'half_open' then
    local lease_until = tonumber(redis.call('HGET', channel_key, 'probe_lease_until') or '0')
    if now >= lease_until then
      redis.call('HSET', channel_key, 'probe_lease_until', tostring(now + lease))
    else
      ok = false
    end
  end
  if ok then
    local priority = tonumber(ARGV[4 + (i - 1) * 3 + 1])
    if best_priority == nil or priority < best_priority then
      best_priority = priority
    end
    table.insert(available, i)
  end
end

if best_priority == nil then
  return 0
end

local tier = {}
local total = 0.0
for _, idx in ipairs(available) do
  local priority = tonumber(ARGV[4 + (idx - 1) * 3 + 1])
  if priority == best_priority then
    local base = tonumber(ARGV[4 + (idx - 1) * 3 + 2])
    local route_key = KEYS[idx]
    local w = tonumber(redis.call('HGET', route_key, 'w'))
    if w == nil then w = base end
    if w < min_w then w = min_w end
    local cw = tonumber(redis.call('HGET', route_key, 'cw') or '0') + w
    redis.call('HSET', route_key, 'cw', string.format('%.6f', cw))
    total = total + w
    table.insert(tier, {index = idx, cw = cw, route_id = ARGV[4 + (idx - 1) * 3 + 3]})
  end
end

if #tier == 0 then
  return 0
end

local pick = tier[1]
for i = 2, #tier do
  local candidate = tier[i]
  if candidate.cw > pick.cw or (candidate.cw == pick.cw and candidate.route_id < pick.route_id) then
    pick = candidate
  end
end
redis.call('HSET', KEYS[pick.index], 'cw', string.format('%.6f', pick.cw - total))

for i = 1, n do
  redis.call('EXPIRE', KEYS[i], ttl)
  redis.call('EXPIRE', KEYS[n + i], ttl)
end
return pick.index
"""

_OUTCOME_SCRIPT = """
local now = tonumber(ARGV[1])
local success = ARGV[2] == '1'
local latency = tonumber(ARGV[3])
local base = tonumber(ARGV[4])
local min_w = tonumber(ARGV[5])
local ratio = tonumber(ARGV[6])
local decay_min = tonumber(ARGV[7])
local decay_high = tonumber(ARGV[8])
local high_mult = tonumber(ARGV[9])
local alpha = tonumber(ARGV[10])
local baseline = tonumber(ARGV[11])
local threshold = tonumber(ARGV[12])
local cooldown = tonumber(ARGV[13])
local ttl = tonumber(ARGV[14])

local route_key = KEYS[1]
local channel_key = KEYS[2]

local function read_number(key, field, fallback)
  local value = tonumber(redis.call('HGET', key, field))
  if value == nil then
    return fallback
  end
  return value
end

local sr = read_number(route_key, 'sr', 1.0)
local lat = read_number(route_key, 'lat', baseline)
local w = read_number(route_key, 'w', base)
if w < min_w then w = min_w end
local route_fail = read_number(route_key, 'fail', 0)
local channel_fail = read_number(channel_key, 'fail', 0)
local state = redis.call('HGET', channel_key, 'state') or 'closed'

if success then
  sr = sr + alpha * (1.0 - sr)
  lat = lat + alpha * (latency - lat)
  local increment = math.max(1.0, base * ratio)
  if state == 'half_open' then
    w = w + increment
  else
    local speed = baseline / math.max(lat, 1.0)
    if speed < 0.25 then
      speed = 0.25
    elseif speed > 2.0 then
      speed = 2.0
    end
    local bonus_ratio = (4.0 * min_w - w) / (3.0 * min_w)
    if bonus_ratio < 0.0 then
      bonus_ratio = 0.0
    elseif bonus_ratio > 1.0 then
      bonus_ratio = 1.0
    end
    local bonus = 1.0 + 2.0 * bonus_ratio
    w = w + increment * sr * speed * bonus
  end
  if w < min_w then w = min_w end
  redis.call('HSET', route_key, 'w', string.format('%.6f', w))
  redis.call('HSET', route_key, 'lat', string.format('%.6f', lat))
  redis.call('HSET', route_key, 'sr', string.format('%.6f', sr))
  redis.call('HSET', route_key, 'fail', '0')
  redis.call('HSET', channel_key, 'state', 'closed')
  redis.call('HSET', channel_key, 'open_until', '0')
  redis.call('HSET', channel_key, 'probe_lease_until', '0')
  redis.call('HSET', channel_key, 'fail', '0')
else
  sr = sr + alpha * (0.0 - sr)
  route_fail = route_fail + 1
  channel_fail = channel_fail + 1
  local high_ref = math.max(base * high_mult, min_w)
  local progress = (w - min_w) / math.max(high_ref - min_w, 0.000000001)
  if progress < 0.0 then
    progress = 0.0
  elseif progress > 1.0 then
    progress = 1.0
  end
  local decay = decay_min - (decay_min - decay_high) * progress
  w = math.max(w * decay, min_w)
  redis.call('HSET', route_key, 'w', string.format('%.6f', w))
  redis.call('HSET', route_key, 'sr', string.format('%.6f', sr))
  redis.call('HSET', route_key, 'fail', tostring(route_fail))
  redis.call('HSET', channel_key, 'fail', tostring(channel_fail))
  if state == 'half_open' or state == 'open' or channel_fail >= threshold then
    redis.call('HSET', channel_key, 'state', 'open')
    redis.call('HSET', channel_key, 'open_until', tostring(now + cooldown))
    redis.call('HSET', channel_key, 'probe_lease_until', '0')
  end
end

redis.call('EXPIRE', route_key, ttl)
redis.call('EXPIRE', channel_key, ttl)
return 1
"""

_PROBE_OUTCOME_SCRIPT = """
local now = tonumber(ARGV[1])
local success = ARGV[2] == '1'
local threshold = tonumber(ARGV[3])
local cooldown = tonumber(ARGV[4])
local ttl = tonumber(ARGV[5])
local latency = tonumber(ARGV[6])

local channel_key = KEYS[1]
local function read_number(field, fallback)
  local value = tonumber(redis.call('HGET', channel_key, field))
  if value == nil then
    return fallback
  end
  return value
end

local state = redis.call('HGET', channel_key, 'state') or 'closed'
local probe_fails = read_number('probe_fails', 0)
local probe_successes = read_number('probe_successes', 0)

if success then
  probe_fails = 0
  probe_successes = probe_successes + 1
  redis.call('HSET', channel_key, 'state', 'closed')
  redis.call('HSET', channel_key, 'open_until', '0')
  redis.call('HSET', channel_key, 'probe_lease_until', '0')
  redis.call('HSET', channel_key, 'fail', '0')
else
  probe_fails = probe_fails + 1
  probe_successes = 0
  if state == 'open' or state == 'half_open' or probe_fails >= threshold then
    redis.call('HSET', channel_key, 'state', 'open')
    redis.call('HSET', channel_key, 'open_until', tostring(now + cooldown))
    redis.call('HSET', channel_key, 'probe_lease_until', '0')
  end
end

redis.call('HSET', channel_key, 'probe_fails', tostring(probe_fails))
redis.call('HSET', channel_key, 'probe_successes', tostring(probe_successes))
redis.call('HSET', channel_key, 'last_probe_at', tostring(now))
redis.call('HSET', channel_key, 'last_probe_ok', success and '1' or '0')
redis.call('HSET', channel_key, 'last_probe_latency_ms', tostring(latency))
redis.call('EXPIRE', channel_key, ttl)
return {redis.call('HGET', channel_key, 'state'), probe_fails, probe_successes}
"""


@dataclass(frozen=True, slots=True)
class ProbeRuntimeResult:
    """一次探测反馈后的渠道运行时状态。"""

    state: str
    probe_fails: int
    probe_successes: int


def build_aimd_config(settings: Settings) -> AimdConfig:
    """把运行配置折算为 AIMD 计算参数。"""

    return AimdConfig(
        min_weight=settings.routing_min_weight,
        success_increment_ratio=settings.routing_aimd_success_increment_ratio,
        decay_at_min=settings.routing_aimd_decay_at_min,
        decay_at_high=settings.routing_aimd_decay_at_high,
        high_weight_multiplier=settings.routing_aimd_high_weight_multiplier,
        ewma_half_life_samples=settings.routing_ewma_half_life_samples,
        latency_baseline_ms=float(settings.routing_latency_baseline_ms),
    )


class RedisChannelRuntime:
    """基于 Redis 的渠道运行时状态实现，供选路、反馈、探测与趋势采样复用。"""

    def __init__(self, client: Redis | None = None, settings: Settings | None = None) -> None:
        self._client = client
        self._settings = settings or get_settings()
        self._select = None
        self._outcome = None
        self._probe = None

    @property
    def client(self) -> Redis:
        return self._client if self._client is not None else get_redis_client()

    def select(self, candidates: list[RuntimeCandidate]) -> UUID | None:
        """按动态熔断状态、最小优先级层与 SWRR 选出唯一路由。"""

        if not candidates:
            return None
        script = self._script("select")
        now_ms = int(time() * 1000)
        keys = [_ROUTE_KEY.format(candidate.route_id) for candidate in candidates]
        keys.extend(_CHANNEL_KEY.format(candidate.channel_id) for candidate in candidates)
        args: list[object] = [
            now_ms,
            self._settings.routing_circuit_probe_lease_seconds * 1000,
            self._settings.routing_min_weight,
            self._settings.routing_state_ttl_seconds,
        ]
        for candidate in candidates:
            args.extend([candidate.priority, candidate.base_weight, str(candidate.route_id)])
        result = int(script(keys=keys, args=args) or 0)
        if result <= 0 or result > len(candidates):
            return None
        return candidates[result - 1].route_id

    def record_outcome(
        self,
        *,
        route_id: UUID,
        channel_id: UUID,
        base_weight: int,
        success: bool,
        latency_ms: int,
    ) -> None:
        """记录一次业务请求结果，原子推进 AIMD 权重与熔断状态。"""

        settings = self._settings
        script = self._script("outcome")
        script(
            keys=[_ROUTE_KEY.format(route_id), _CHANNEL_KEY.format(channel_id)],
            args=[
                int(time() * 1000),
                1 if success else 0,
                max(int(latency_ms), 0),
                base_weight,
                settings.routing_min_weight,
                settings.routing_aimd_success_increment_ratio,
                settings.routing_aimd_decay_at_min,
                settings.routing_aimd_decay_at_high,
                settings.routing_aimd_high_weight_multiplier,
                build_aimd_config(settings).ewma_alpha,
                settings.routing_latency_baseline_ms,
                settings.routing_circuit_failure_threshold,
                settings.routing_circuit_cooldown_seconds * 1000,
                settings.routing_state_ttl_seconds,
            ],
        )

    def record_probe_outcome(self, *, channel_id: UUID, success: bool, latency_ms: int) -> ProbeRuntimeResult:
        """记录一次健康探测结果，只更新渠道级熔断与探测计数。"""

        settings = self._settings
        script = self._script("probe")
        state, probe_fails, probe_successes = script(
            keys=[_CHANNEL_KEY.format(channel_id)],
            args=[
                int(time() * 1000),
                1 if success else 0,
                settings.routing_circuit_failure_threshold,
                settings.routing_circuit_cooldown_seconds * 1000,
                settings.routing_state_ttl_seconds,
                max(int(latency_ms), 0),
            ],
        )
        return ProbeRuntimeResult(
            state=_text(state), probe_fails=int(probe_fails), probe_successes=int(probe_successes)
        )

    def read_route_state(self, route_id: UUID) -> dict[str, str]:
        return dict(self.client.hgetall(_ROUTE_KEY.format(route_id)))

    def read_channel_state(self, channel_id: UUID) -> dict[str, str]:
        return dict(self.client.hgetall(_CHANNEL_KEY.format(channel_id)))

    def read_route_states(self, route_ids: list[UUID]) -> dict[UUID, dict[str, str]]:
        """批量读取路由运行时状态，避免趋势采样逐条往返。"""

        if not route_ids:
            return {}
        pipe = self.client.pipeline(transaction=False)
        for route_id in route_ids:
            pipe.hgetall(_ROUTE_KEY.format(route_id))
        return {route_id: dict(values) for route_id, values in zip(route_ids, pipe.execute(), strict=True)}

    def reset_channel(self, *, channel_id: UUID, route_ids: list[UUID]) -> None:
        """清除渠道及其全部路由的运行时状态，用于自动恢复后回到初始权重。"""

        keys = [_CHANNEL_KEY.format(channel_id)]
        keys.extend(_ROUTE_KEY.format(route_id) for route_id in route_ids)
        self.client.delete(*keys)

    def reset_routes(self, route_ids: list[UUID]) -> None:
        """仅清除路由级状态，管理员调整初始权重或优先级后让新配置立即生效。"""

        if not route_ids:
            return
        self.client.delete(*(_ROUTE_KEY.format(route_id) for route_id in route_ids))

    def _script(self, name: str):
        cached = getattr(self, f"_{name}", None)
        if cached is not None:
            return cached
        source = {"select": _SELECT_SCRIPT, "outcome": _OUTCOME_SCRIPT, "probe": _PROBE_OUTCOME_SCRIPT}[name]
        cached = self.client.register_script(source)
        setattr(self, f"_{name}", cached)
        return cached


@lru_cache
def get_channel_runtime() -> RedisChannelRuntime:
    """返回进程内复用的运行时实例，避免每次请求重复注册 Lua 脚本。"""

    return RedisChannelRuntime()


def _text(value: object) -> str:
    """把可能为 bytes 的 Redis 返回值统一转换为字符串。"""

    return value.decode() if isinstance(value, bytes) else str(value)
