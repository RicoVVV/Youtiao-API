"""服务器资源快照的派生指标计算。

使用率与速率一律由相邻两次采样的原始累计量差值推算，而不是读取采样函数自报的瞬时值：
差值结果只依赖数据库中的上一行，因此领导实例切换、进程重启与漏采窗口都不会产生错误读数。
上一行缺失（首次采集、计数器不可比）时，派生字段写 ``None`` 而不是 0。
落入 JSONB 的派生值统一转为 ``float``，落到数值列的派生值保持 ``Decimal``。
"""

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from app.infrastructure.system_metrics import NetworkCounters, SystemMetricSample
from app.modules.monitoring.model import ServerMetricSnapshot

QUANTUM = Decimal("0.001")
"""落库精度，与快照表各数值列的小数位定义一致。"""


def build_snapshot_values(
    *, window_start: datetime, sample: SystemMetricSample, previous: ServerMetricSnapshot | None
) -> dict:
    """把一次采样与上一行快照组装为快照表字段。"""

    interval_seconds = _interval_seconds(previous, window_start)
    busiest = _busiest_disk(sample)
    return {
        "window_start": window_start,
        "sample_interval_seconds": _as_decimal(interval_seconds),
        "cpu_usage_percent": _usage_from_counters(
            previous.cpu_total_seconds if previous else None,
            previous.cpu_idle_seconds if previous else None,
            sample.cpu.total_seconds,
            sample.cpu.idle_seconds,
        ),
        "cpu_total_seconds": _as_decimal(sample.cpu.total_seconds),
        "cpu_idle_seconds": _as_decimal(sample.cpu.idle_seconds),
        "cpu_core_count": len(sample.cpu.per_core),
        "cpu_per_core_percent": _per_core_percent(previous, sample),
        "cpu_per_core_counters": [[total, idle] for total, idle in sample.cpu.per_core],
        "load1": _as_decimal(sample.load1),
        "load5": _as_decimal(sample.load5),
        "load15": _as_decimal(sample.load15),
        "memory_total_bytes": sample.memory.total_bytes if sample.memory else None,
        "memory_used_bytes": sample.memory.used_bytes if sample.memory else None,
        "memory_usage_percent": _memory_percent(sample.memory),
        "swap_total_bytes": sample.swap.total_bytes if sample.swap else None,
        "swap_used_bytes": sample.swap.used_bytes if sample.swap else None,
        "swap_usage_percent": _memory_percent(sample.swap),
        "network_interfaces": _network_rows(sample.network, previous, interval_seconds),
        "disks": _disk_rows(sample),
        "max_disk_usage_percent": None if busiest is None else busiest[1],
        "max_disk_mount": None if busiest is None else busiest[0],
    }


def usage_percent(used_bytes: int, total_bytes: int) -> Decimal | None:
    """按已用量与总量计算百分比，总量不可用时返回 ``None``。"""

    if total_bytes <= 0:
        return None
    return _quantize_percent(Decimal(used_bytes) / Decimal(total_bytes) * 100)


def _usage_from_counters(
    previous_total: Decimal | None,
    previous_idle: Decimal | None,
    total_seconds: float,
    idle_seconds: float,
) -> Decimal | None:
    """由累计时间的差值计算 CPU 使用率，缺少可比的上一次累计量时返回 ``None``。"""

    if previous_total is None or previous_idle is None:
        return None
    total_delta = Decimal(str(total_seconds)) - Decimal(previous_total)
    idle_delta = Decimal(str(idle_seconds)) - Decimal(previous_idle)
    if total_delta <= 0:
        return None
    return _quantize_percent((total_delta - idle_delta) / total_delta * 100)


def _per_core_percent(previous: ServerMetricSnapshot | None, sample: SystemMetricSample) -> list | None:
    """逐核计算使用率，核数变化或缺少上一次计数时整体返回 ``None``。"""

    counters = previous.cpu_per_core_counters if previous else None
    per_core = sample.cpu.per_core
    if not counters or len(counters) != len(per_core):
        return None
    values: list[Decimal] = []
    for last, (total_seconds, idle_seconds) in zip(counters, per_core, strict=True):
        if not isinstance(last, list) or len(last) != 2:
            return None
        usage = _usage_from_counters(Decimal(str(last[0])), Decimal(str(last[1])), total_seconds, idle_seconds)
        values.append(Decimal("0") if usage is None else usage)
    return [_as_float(value) for value in values]


def _network_rows(
    interfaces: tuple[NetworkCounters, ...],
    previous: ServerMetricSnapshot | None,
    interval_seconds: float | None,
) -> list[dict]:
    """组装各网卡的累计量与收发速率，缺少可比的上一次累计量时速率为 ``None``。"""

    last_rows = previous.network_interfaces if previous else None
    previous_by_name = {row["name"]: row for row in (last_rows or []) if isinstance(row, dict) and "name" in row}
    return [
        {
            "name": counters.name,
            "rx_bytes": counters.rx_bytes,
            "tx_bytes": counters.tx_bytes,
            "rx_rate_bps": _rate(previous_by_name.get(counters.name), "rx_bytes", counters.rx_bytes, interval_seconds),
            "tx_rate_bps": _rate(previous_by_name.get(counters.name), "tx_bytes", counters.tx_bytes, interval_seconds),
            "rx_errors": counters.rx_errors,
            "tx_errors": counters.tx_errors,
            "rx_dropped": counters.rx_dropped,
            "tx_dropped": counters.tx_dropped,
        }
        for counters in interfaces
    ]


def _rate(previous_row: dict | None, key: str, current_value: int, interval_seconds: float | None) -> float | None:
    """按累计量差值与实际间隔计算速率，网卡重新计数或缺少上一次数据时返回 ``None``。

    返回值转为浮点：速率最终落入 JSONB 列，``Decimal`` 无法被 JSON 序列化。
    """

    if previous_row is None or not interval_seconds or interval_seconds <= 0:
        return None
    previous_value = previous_row.get(key)
    if not isinstance(previous_value, int) or current_value < previous_value:
        return None
    rate = Decimal(current_value - previous_value) / Decimal(str(interval_seconds))
    return _as_float(rate.quantize(QUANTUM, rounding=ROUND_HALF_UP))


def _disk_rows(sample: SystemMetricSample) -> list[dict]:
    """组装各挂载点的容量明细，使用率转为 ``float`` 供 JSONB 保存。"""

    rows: list[dict] = []
    for disk in sample.disks:
        percent = usage_percent(disk.used_bytes, disk.total_bytes)
        rows.append(
            {
                "mount": disk.mount,
                "total_bytes": disk.total_bytes,
                "used_bytes": disk.used_bytes,
                "usage_percent": None if percent is None else _as_float(percent),
            }
        )
    return rows


def _busiest_disk(sample: SystemMetricSample) -> tuple[str, Decimal] | None:
    """返回使用率最高的挂载点及其使用率，供磁盘告警直接判定与文案展示。"""

    candidates = [(disk.mount, usage_percent(disk.used_bytes, disk.total_bytes)) for disk in sample.disks]
    usable = [(mount, percent) for mount, percent in candidates if percent is not None]
    if not usable:
        return None
    return max(usable, key=lambda item: item[1])


def _memory_percent(counters) -> Decimal | None:
    """计算内存或交换分区使用率，宿主未提供该容量时返回 ``None``。"""

    if counters is None:
        return None
    return usage_percent(counters.used_bytes, counters.total_bytes)


def _interval_seconds(previous: ServerMetricSnapshot | None, window_start: datetime) -> float | None:
    """返回本次采样与上一行的实际间隔秒数，用于把累计量差值换算为速率。"""

    if previous is None:
        return None
    seconds = (window_start - previous.window_start).total_seconds()
    return seconds if seconds > 0 else None


def _quantize_percent(value: Decimal) -> Decimal:
    """把百分比收敛到 ``[0, 100]`` 与列定义精度，消除计数器回绕与浮点误差。"""

    bounded = min(max(value, Decimal("0")), Decimal("100"))
    return bounded.quantize(QUANTUM, rounding=ROUND_HALF_UP)


def _as_decimal(value: float | None) -> Decimal | None:
    """把浮点计数转换为定点小数，空值原样返回。"""

    if value is None:
        return None
    return Decimal(str(value)).quantize(QUANTUM, rounding=ROUND_HALF_UP)


def _as_float(value: Decimal) -> float:
    """把定点小数转为浮点，便于写入 JSONB 列。"""

    return float(value)
