"""资源采集适配层，支持「宿主整机」与「采集本机」两种口径。

宿主模式（生产）：CPU、内存读宿主 procfs，磁盘容量读宿主根分区所在文件系统。
两处必须绕开 psutil 的高层接口：

- 负载：``psutil.getloadavg()`` 内部走 ``os.getloadavg()``，路径写死 ``/proc/loadavg``，
  不受 ``PROCFS_PATH`` 影响，只能直接读取宿主文件；
- 网络：``/proc/net`` 是指向 ``self/net`` 的符号链接，挂载宿主 procfs 后仍解析回
  读取者所在的网络命名空间，因此只有读取宿主 PID 1 的 ``net/dev`` 才能得到整机流量。

本机模式（本地开发）：直接使用 psutil 的本机接口，不需要任何宿主挂载。
Windows 不提供负载概念，该模式下负载字段为空而不是假的 0。

两种口径的数据不可混用比较：本机模式采到的是运行进程的这台机器，容器部署时它是容器自身而非宿主机。

本模块只产出原始累计量，不计算使用率与速率：派生指标由应用层按相邻两次采样差值推算，
使结果不依赖进程内状态，也不受领导实例切换影响。
"""

import logging
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import psutil

from app.core.config import Settings

logger = logging.getLogger(__name__)

HOST_INIT_PID = 1
"""宿主 PID 1，其网络命名空间即宿主整机网络命名空间。"""

_NATIVE_PROCFS_PATH = getattr(psutil, "PROCFS_PATH", None)
"""本机默认 procfs 路径；Windows 的 psutil 不使用 procfs，该值为空。"""

_NET_DEV_HEADER_LINES = 2
"""``net/dev`` 固定以两行表头开头，数据行从第三行开始。"""

_NET_DEV_REQUIRED_FIELDS = 16
"""单张网卡的收发计数固定为 16 个字段：前 8 个收、后 8 个发。"""


@dataclass(frozen=True, slots=True)
class CpuTimes:
    """一次 CPU 累计时间采样，单位秒。"""

    total_seconds: float
    idle_seconds: float
    per_core: tuple[tuple[float, float], ...]


@dataclass(frozen=True, slots=True)
class NetworkCounters:
    """单张网卡的累计收发计数。"""

    name: str
    rx_bytes: int
    tx_bytes: int
    rx_errors: int
    tx_errors: int
    rx_dropped: int
    tx_dropped: int


@dataclass(frozen=True, slots=True)
class MemoryCounters:
    """内存或交换分区的容量与已用量，单位字节。"""

    total_bytes: int
    used_bytes: int


@dataclass(frozen=True, slots=True)
class DiskCounters:
    """单个挂载点的容量与已用量，单位字节。"""

    mount: str
    total_bytes: int
    used_bytes: int


@dataclass(frozen=True, slots=True)
class SystemMetricSample:
    """一次采样的原始值。"""

    cpu: CpuTimes
    load1: float | None
    load5: float | None
    load15: float | None
    memory: MemoryCounters | None
    swap: MemoryCounters | None
    network: tuple[NetworkCounters, ...]
    disks: tuple[DiskCounters, ...]


def sample_system_metrics(settings: Settings) -> SystemMetricSample:
    """按配置的采集口径采样一次资源原始值。"""

    if not settings.monitoring_server_host_mode:
        return _sample_local_metrics(settings)
    return _sample_host_metrics(settings)


def _sample_host_metrics(settings: Settings) -> SystemMetricSample:
    """采集宿主整机资源。

    把 psutil 的 procfs 根指向宿主路径，使 CPU 与内存读取宿主数据；负载与网络不受该设置影响，
    由本模块直接读取宿主文件。该全局变量仅在本模块内使用，进程内不得再依赖 psutil 的其它默认路径。
    """

    proc_path = settings.monitoring_server_proc_path
    _use_procfs_path(str(proc_path))
    load1, load5, load15 = read_load_average(proc_path)
    return SystemMetricSample(
        cpu=read_cpu_times(),
        load1=load1,
        load5=load5,
        load15=load15,
        memory=read_memory_counters(),
        swap=read_swap_counters(),
        network=read_network_counters(proc_path),
        disks=read_disk_counters(settings.monitoring_server_disk_paths),
    )


def _sample_local_metrics(settings: Settings) -> SystemMetricSample:
    """采集运行本进程的机器，供本地开发使用。

    主动还原 procfs 根，避免同进程内两种口径的调用互相污染 psutil 的全局配置。
    """

    _use_procfs_path(_NATIVE_PROCFS_PATH)
    load = read_local_load_average()
    return SystemMetricSample(
        cpu=read_cpu_times(),
        load1=None if load is None else load[0],
        load5=None if load is None else load[1],
        load15=None if load is None else load[2],
        memory=read_memory_counters(),
        swap=read_swap_counters(),
        network=read_local_network_counters(),
        disks=read_disk_counters(settings.monitoring_server_disk_paths),
    )


def _use_procfs_path(proc_path: str | None) -> None:
    """把 psutil 的 procfs 根切到指定路径。

    Windows 的 psutil 不使用 procfs，模块上不存在该配置项，此时直接跳过：
    CPU、内存由 psutil 的 Windows 本机接口读取。
    """

    if proc_path is None or not hasattr(psutil, "PROCFS_PATH"):
        return
    psutil.PROCFS_PATH = proc_path


def read_local_load_average() -> tuple[float, float, float] | None:
    """读取本机平均负载，系统不提供负载概念时返回空。

    Windows 上 ``psutil.getloadavg()`` 不报错但恒返回 0，直接使用会把"平台不支持"渲染成真实的零负载。
    """

    if sys.platform == "win32":
        return None
    return psutil.getloadavg()


def read_local_network_counters() -> tuple[NetworkCounters, ...]:
    """读取本机各网卡的累计收发计数，按网卡名排序。"""

    counters = psutil.net_io_counters(pernic=True)
    return tuple(
        NetworkCounters(
            name=name,
            rx_bytes=int(item.bytes_recv),
            tx_bytes=int(item.bytes_sent),
            rx_errors=int(item.errin),
            tx_errors=int(item.errout),
            rx_dropped=int(item.dropin),
            tx_dropped=int(item.dropout),
        )
        for name, item in sorted(counters.items())
    )


def read_cpu_times() -> CpuTimes:
    """读取宿主 CPU 累计时间，整体与每核分别记录总时间与空闲时间。"""

    overall = psutil.cpu_times()
    per_core = psutil.cpu_times(percpu=True)
    return CpuTimes(
        total_seconds=_total_seconds(overall),
        idle_seconds=_idle_seconds(overall),
        per_core=tuple((_total_seconds(core), _idle_seconds(core)) for core in per_core),
    )


def read_memory_counters() -> MemoryCounters | None:
    """读取宿主物理内存容量与已用量，已用量按总量减可用量计算。"""

    memory = psutil.virtual_memory()
    if not memory.total:
        return None
    return MemoryCounters(total_bytes=int(memory.total), used_bytes=int(memory.total - memory.available))


def read_swap_counters() -> MemoryCounters | None:
    """读取宿主交换分区容量与已用量，宿主未启用交换分区时返回空。"""

    swap = psutil.swap_memory()
    if not swap.total:
        return None
    return MemoryCounters(total_bytes=int(swap.total), used_bytes=int(swap.used))


def read_disk_counters(paths: Sequence[str]) -> tuple[DiskCounters, ...]:
    """读取各路径所在文件系统的容量，路径不可用时跳过并记录告警日志。"""

    counters: list[DiskCounters] = []
    for path in paths:
        try:
            usage = psutil.disk_usage(path)
        except OSError as exc:
            logger.warning("服务器资源监控：磁盘路径不可用 path=%s error=%s", path, exc)
            continue
        counters.append(DiskCounters(mount=path, total_bytes=int(usage.total), used_bytes=int(usage.used)))
    return tuple(counters)


def read_network_counters(proc_path: Path) -> tuple[NetworkCounters, ...]:
    """读取宿主网络命名空间的网卡累计计数，不可读时返回空。"""

    net_dev = proc_path / str(HOST_INIT_PID) / "net" / "dev"
    try:
        text = net_dev.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("服务器资源监控：宿主网络计数不可读 path=%s error=%s", net_dev, exc)
        return ()
    return parse_net_dev(text)


def read_load_average(proc_path: Path) -> tuple[float, float, float]:
    """读取宿主 1、5、15 分钟平均负载。"""

    return parse_loadavg((proc_path / "loadavg").read_text(encoding="utf-8"))


def parse_loadavg(text: str) -> tuple[float, float, float]:
    """解析 ``loadavg`` 的前三个字段为 1、5、15 分钟负载。"""

    fields = text.split()
    if len(fields) < 3:
        raise ValueError("loadavg 内容格式不正确")
    return float(fields[0]), float(fields[1]), float(fields[2])


def parse_net_dev(text: str) -> tuple[NetworkCounters, ...]:
    """解析 ``net/dev`` 内容为各网卡的累计收发计数，按网卡名排序。"""

    counters: list[NetworkCounters] = []
    for line in text.splitlines()[_NET_DEV_HEADER_LINES:]:
        name, separator, rest = line.partition(":")
        fields = rest.split()
        if not separator or len(fields) < _NET_DEV_REQUIRED_FIELDS:
            continue
        counters.append(
            NetworkCounters(
                name=name.strip(),
                rx_bytes=int(fields[0]),
                rx_errors=int(fields[2]),
                rx_dropped=int(fields[3]),
                tx_bytes=int(fields[8]),
                tx_errors=int(fields[10]),
                tx_dropped=int(fields[11]),
            )
        )
    return tuple(sorted(counters, key=lambda item: item.name))


def _total_seconds(times) -> float:
    """累计 CPU 时间总和，不含已计入 user 与 nice 的 guest 时间。

    各平台字段并不一致（Windows 没有 nice，iowait/irq/softirq/steal 只有 Linux 才有），
    缺失字段按 0 计，避免在非 Linux 环境抛属性错误。
    """

    return float(
        times.user
        + getattr(times, "nice", 0.0)
        + times.system
        + times.idle
        + getattr(times, "iowait", 0.0)
        + getattr(times, "irq", 0.0)
        + getattr(times, "softirq", 0.0)
        + getattr(times, "steal", 0.0)
    )


def _idle_seconds(times) -> float:
    """空闲时间按 ``idle + iowait`` 计算，与 psutil 的 CPU 使用率口径保持一致。"""

    return float(times.idle) + float(getattr(times, "iowait", 0.0))
