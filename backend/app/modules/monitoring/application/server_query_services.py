"""服务器资源监控查询用例，服务于管理侧只读接口。

返回结构沿用分组监控的「图表即取即用」约定：趋势接口给出等长的 x 轴与序列，
缺失窗口补 ``null`` 而不是跳过；尚无数据时返回空结构而不是报错。
"""

from datetime import UTC, datetime
from decimal import Decimal

from sqlmodel import Session

from app.modules.monitoring.application.window import (
    SERVER_WINDOW_MINUTES,
    floor_server_window,
    recent_server_windows,
)
from app.modules.monitoring.crud.server_metric_crud import ServerMetricCrud
from app.modules.monitoring.model import ServerMetricSnapshot

_LOOPBACK_NAMES = frozenset({"lo", "lo0"})
"""Linux 与 macOS 的回环网卡名；Windows 的回环网卡名按关键字识别，见 ``_is_loopback``。"""

_SERIES = (
    ("cpu.usage_percent", "CPU 使用率", "percent", "cpu"),
    ("memory.usage_percent", "内存使用率", "percent", "memory"),
    ("swap.usage_percent", "交换分区使用率", "percent", "memory"),
    ("load.load1", "1 分钟负载", "count", "load"),
    ("load.load5", "5 分钟负载", "count", "load"),
    ("load.load15", "15 分钟负载", "count", "load"),
    ("disk.usage_percent", "磁盘使用率", "percent", "disk"),
    ("network.rx_rate_bps", "网络下行速率", "bytes_per_second", "network"),
    ("network.tx_rate_bps", "网络上行速率", "bytes_per_second", "network"),
)
"""趋势接口输出的序列定义：键、展示名、单位与分组。"""


class ServerMetricQueryApplicationService:
    """服务器资源监控的读取用例：最新快照与窗口序列。"""

    def __init__(self, session: Session) -> None:
        """绑定调用方提供的事务会话。"""

        self._snapshots = ServerMetricCrud(session)

    def latest(self) -> dict:
        """返回最新一次采样结果，含各挂载点与各网卡明细。"""

        snapshot = self._snapshots.get_latest()
        return {
            "has_data": snapshot is not None,
            "window_minutes": SERVER_WINDOW_MINUTES,
            **_snapshot_view(snapshot),
        }

    def trend(self, *, hours: int) -> dict:
        """返回最近若干小时的 1 分钟粒度资源序列。"""

        newest = floor_server_window(datetime.now(UTC))
        windows = recent_server_windows(newest=newest, count=hours * 60)
        snapshots = self._snapshots.list_range(start_at=windows[0], end_at=windows[-1])
        flattened = {snapshot.window_start: _flatten(snapshot) for snapshot in snapshots}
        return {
            "window_minutes": SERVER_WINDOW_MINUTES,
            "x_axis": [window.isoformat() for window in windows],
            "series": [
                {
                    "key": key,
                    "name": name,
                    "unit": unit,
                    "group": group,
                    "values": [flattened.get(window, {}).get(key) for window in windows],
                }
                for key, name, unit, group in _SERIES
            ],
        }


def _snapshot_view(snapshot: ServerMetricSnapshot | None) -> dict:
    """把快照行转换为前端可直接渲染的结构，无数据时各项为空。"""

    if snapshot is None:
        return {
            "window_start": None,
            "sample_interval_seconds": None,
            "cpu": {"usage_percent": None, "core_count": 0, "per_core_percent": []},
            "load": {"load1": None, "load5": None, "load15": None},
            "memory": _capacity_view(None, None, None),
            "swap": _capacity_view(None, None, None),
            "network_interfaces": [],
            "disks": [],
            "max_disk_mount": None,
            "max_disk_usage_percent": None,
        }
    return {
        "window_start": snapshot.window_start.isoformat(),
        "sample_interval_seconds": _optional_float(snapshot.sample_interval_seconds),
        "cpu": {
            "usage_percent": _optional_float(snapshot.cpu_usage_percent),
            "core_count": snapshot.cpu_core_count,
            "per_core_percent": snapshot.cpu_per_core_percent or [],
        },
        "load": {
            "load1": _optional_float(snapshot.load1),
            "load5": _optional_float(snapshot.load5),
            "load15": _optional_float(snapshot.load15),
        },
        "memory": _capacity_view(
            snapshot.memory_total_bytes, snapshot.memory_used_bytes, snapshot.memory_usage_percent
        ),
        "swap": _capacity_view(snapshot.swap_total_bytes, snapshot.swap_used_bytes, snapshot.swap_usage_percent),
        "network_interfaces": snapshot.network_interfaces or [],
        "disks": snapshot.disks or [],
        "max_disk_mount": snapshot.max_disk_mount,
        "max_disk_usage_percent": _optional_float(snapshot.max_disk_usage_percent),
    }


def _capacity_view(total_bytes: int | None, used_bytes: int | None, percent: Decimal | None) -> dict:
    """构造内存或交换分区的容量投影。"""

    return {
        "total_bytes": total_bytes,
        "used_bytes": used_bytes,
        "usage_percent": _optional_float(percent),
    }


def _flatten(snapshot: ServerMetricSnapshot) -> dict:
    """把一行快照展开为「序列键到取值」的扁平映射。"""

    rx_rate, tx_rate = _network_totals(snapshot.network_interfaces)
    return {
        "cpu.usage_percent": _optional_float(snapshot.cpu_usage_percent),
        "memory.usage_percent": _optional_float(snapshot.memory_usage_percent),
        "swap.usage_percent": _optional_float(snapshot.swap_usage_percent),
        "load.load1": _optional_float(snapshot.load1),
        "load.load5": _optional_float(snapshot.load5),
        "load.load15": _optional_float(snapshot.load15),
        "disk.usage_percent": _optional_float(snapshot.max_disk_usage_percent),
        "network.rx_rate_bps": rx_rate,
        "network.tx_rate_bps": tx_rate,
    }


def _network_totals(interfaces: list | None) -> tuple[float | None, float | None]:
    """汇总非回环网卡的收发速率，全部网卡都无可用速率时返回空。"""

    rx_total: float | None = None
    tx_total: float | None = None
    for row in interfaces or []:
        if not isinstance(row, dict) or _is_loopback(row.get("name")):
            continue
        rx_total = _accumulate(rx_total, row.get("rx_rate_bps"))
        tx_total = _accumulate(tx_total, row.get("tx_rate_bps"))
    return rx_total, tx_total


def _is_loopback(name) -> bool:
    """判断是否回环网卡：它的收发量不对外，计入会显著虚高整机流量。

    除 ``lo`` / ``lo0`` 外，Windows 的回环网卡名形如 ``Loopback Pseudo-Interface 1``，按关键字匹配。
    """

    if not isinstance(name, str):
        return False
    normalized = name.strip().lower()
    return normalized in _LOOPBACK_NAMES or "loopback" in normalized


def _accumulate(total: float | None, value) -> float | None:
    """把单个网卡的速率累加到合计值，非数值取值直接忽略。"""

    if isinstance(value, bool) or not isinstance(value, int | float):
        return total
    return (total or 0.0) + float(value)


def _optional_float(value: Decimal | float | None) -> float | None:
    """把定点小数或浮点转为浮点，空值原样返回。"""

    return None if value is None else float(value)
