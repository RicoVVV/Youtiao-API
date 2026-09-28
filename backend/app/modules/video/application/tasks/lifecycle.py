"""视频任务应用状态机，校验用例和 Worker 的合法状态转换。

本模块只维护内存中的转换白名单，不执行数据库读写；调用方在事务中持久化通过校验后的状态与审计事件。
"""

from collections.abc import Mapping

from app.modules.video.model.video_task import VideoTaskStatus


class InvalidVideoTaskTransition(ValueError):
    """表示调用方尝试执行未获允许的任务状态转移。"""


_ALLOWED_TRANSITIONS: Mapping[VideoTaskStatus, set[VideoTaskStatus]] = {
    VideoTaskStatus.submitting: {
        VideoTaskStatus.queued,
        VideoTaskStatus.processing,
        VideoTaskStatus.failed,
        VideoTaskStatus.submission_unknown,
        VideoTaskStatus.cancelled,
    },
    VideoTaskStatus.submission_unknown: {
        VideoTaskStatus.queued,
        VideoTaskStatus.processing,
        VideoTaskStatus.failed,
        VideoTaskStatus.cancelled,
    },
    VideoTaskStatus.queued: {
        VideoTaskStatus.processing,
        VideoTaskStatus.succeeded,
        VideoTaskStatus.failed,
        VideoTaskStatus.cancelled,
        VideoTaskStatus.timed_out,
    },
    VideoTaskStatus.processing: {
        VideoTaskStatus.succeeded,
        VideoTaskStatus.failed,
        VideoTaskStatus.cancelled,
        VideoTaskStatus.timed_out,
    },
    VideoTaskStatus.succeeded: {VideoTaskStatus.failed},
    VideoTaskStatus.failed: set(),
    VideoTaskStatus.cancelled: set(),
    VideoTaskStatus.timed_out: set(),
}


def ensure_transition(source: VideoTaskStatus, target: VideoTaskStatus) -> None:
    """校验任务从 source 到 target 的转移是否合法。

    参数为任务当前状态和目标状态；非法转换抛出 InvalidVideoTaskTransition，避免迟到消息覆盖终态。
    """

    # 重复消息须先由调用方识别当前状态，避免无意义转换伪造审计事件。
    if target not in _ALLOWED_TRANSITIONS[source]:
        raise InvalidVideoTaskTransition(f"不允许视频任务从 {source.value} 转移到 {target.value}")
