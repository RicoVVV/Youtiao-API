"""进程内存维护：定期回收循环引用垃圾，并把已释放的堆内存归还操作系统。

CPython 释放对象后不会自动把内存还给操作系统：pymalloc 的 arena 与 glibc 的空闲页都会留在进程内，
视频成品这类数十 MB 的临时峰值过后，RSS 仍可能长期停在峰值附近。本模块在独立后台任务中定期执行
``gc.collect()`` 并调用 glibc ``malloc_trim``，避免临时峰值固化为常驻内存；回收结果写入日志，
便于把「内存只涨不降」与业务泄漏区分开。
"""

import asyncio
import ctypes
import gc
import logging
import sys

import psutil

logger = logging.getLogger(__name__)


def process_rss_bytes() -> int | None:
    """返回当前进程的常驻内存字节数，读取失败时返回空值。"""

    try:
        return psutil.Process().memory_info().rss
    except psutil.Error:
        return None


def _malloc_trim() -> bool:
    """调用 glibc ``malloc_trim`` 归还空闲堆页；非 glibc 运行环境直接跳过。"""

    if sys.platform != "linux":
        return False
    try:
        libc = ctypes.CDLL(None)
        trim = libc.malloc_trim
    except (OSError, AttributeError):
        return False
    trim.argtypes = [ctypes.c_size_t]
    trim.restype = ctypes.c_int
    try:
        return bool(trim(0))
    except OSError:
        return False


def trim_process_memory() -> dict[str, int | bool | None]:
    """执行一次内存回收，返回回收对象数、堆归还结果与回收前后 RSS。

    参数：无。
    返回值：可直接作为结构化日志字段的回收快照。
    副作用：执行一次全量垃圾回收；Linux 上额外触发一次 glibc 堆整理。
    """

    rss_before = process_rss_bytes()
    collected = gc.collect()
    trimmed = _malloc_trim()
    return {
        "collected_objects": collected,
        "heap_trimmed": trimmed,
        "rss_before_bytes": rss_before,
        "rss_after_bytes": process_rss_bytes(),
    }


async def run_memory_maintenance(interval_seconds: int) -> None:
    """按周期回收进程内存；单次失败只记日志，不终止后台任务。

    回收放在独立线程执行：全量 GC 会短暂持有 GIL，留在事件循环里会拖慢同一 worker 上的在途请求。
    """

    while True:
        await asyncio.sleep(interval_seconds)
        try:
            result = await asyncio.to_thread(trim_process_memory)
        except Exception:
            logger.exception("进程内存回收失败")
            continue
        logger.info("进程内存回收完成", extra=result)
