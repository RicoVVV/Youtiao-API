"""监控窗口的时间计算，集中定义窗口长度、对齐方式与查询可见窗口。

窗口按 ``completed_at`` 归属：视频这类异步任务在创建时状态为预占、耗时为空的记录，
会落在它真正完成时刻所在的窗口，而不是创建时刻的窗口。
"""

from datetime import UTC, datetime, timedelta

WINDOW_MINUTES = 5
"""监控窗口长度，固定 5 分钟。"""

WINDOW_DELTA = timedelta(minutes=WINDOW_MINUTES)

SERVER_WINDOW_MINUTES = 1
"""服务器资源采样窗口长度，固定 1 分钟。"""

SERVER_WINDOW_DELTA = timedelta(minutes=SERVER_WINDOW_MINUTES)

WINDOWS_PER_HOUR = 60 // WINDOW_MINUTES
"""每小时的窗口数量。"""

WINDOWS_PER_DAY = 24 * WINDOWS_PER_HOUR
"""每天的窗口数量，用于近 24 小时汇总与趋势取点。"""

CATCH_UP_WINDOWS = 6
"""聚合任务每次最多回补的历史窗口数，用于覆盖调度延迟导致的窗口缺口。"""


def floor_window(moment: datetime) -> datetime:
    """把时刻向下取整到 5 分钟对齐的窗口起点。"""

    aware = moment.astimezone(UTC)
    return aware.replace(minute=aware.minute - aware.minute % WINDOW_MINUTES, second=0, microsecond=0)


def newest_window(now: datetime) -> datetime:
    """返回当前应当已完成聚合并对查询可见的最新窗口起点。

    比"最近一个已结束窗口"再往前一个窗口，留出结算写入落稳的时间，
    使窗口末尾刚完成、事务尚未提交的请求也能被统计到。
    """

    return floor_window(now) - 2 * WINDOW_DELTA


def window_end(window_start: datetime) -> datetime:
    """返回窗口的结束时刻（不含）。"""

    return window_start + WINDOW_DELTA


def floor_server_window(moment: datetime) -> datetime:
    """把时刻向下取整到 1 分钟对齐的资源采样窗口起点。"""

    return moment.astimezone(UTC).replace(second=0, microsecond=0)


def recent_server_windows(*, newest: datetime, count: int) -> list[datetime]:
    """返回截至 ``newest`` 的连续 1 分钟窗口起点，按时间升序。"""

    return [newest - index * SERVER_WINDOW_DELTA for index in range(count - 1, -1, -1)]


def recent_windows(*, newest: datetime, count: int) -> list[datetime]:
    """返回截至 ``newest`` 的连续窗口起点，按时间升序。"""

    return [newest - index * WINDOW_DELTA for index in range(count - 1, -1, -1)]
