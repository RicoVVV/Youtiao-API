"""视频任务及其审计、上游尝试记录的数据库访问。

本模块集中任务创建、用户隔离查询和状态裁决所需行锁，不处理状态机校验、计费或事务提交。
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.video.model.video_task import TaskEvent, VideoTask, VideoTaskStatus


class VideoTaskCrud:
    """封装视频任务关联数据的 ORM 操作。"""

    def __init__(self, session: Session) -> None:
        """绑定调用方提供的事务会话。"""

        self._session = session

    def refresh(self, task: VideoTask) -> None:
        self._session.refresh(task)

    def create(self, task: VideoTask) -> VideoTask:
        """加入新任务并刷新主键，以支持同一事务关联报价和账本记录。"""

        self._session.add(task)
        self._session.flush()
        return task

    def get(self, *, task_id: UUID) -> VideoTask | None:
        return self._session.get(VideoTask, task_id)

    def list_by_user(self, *, user_id: UUID) -> list[VideoTask]:
        """按创建时间倒序读取用户任务，确保 API 查询不跨用户泄露数据。"""

        return list(
            self._session.scalars(
                select(VideoTask).where(VideoTask.user_id == user_id).order_by(VideoTask.created_at.desc())
            )
        )

    def get_owned(self, *, task_id: UUID, user_id: UUID) -> VideoTask | None:
        """读取指定用户拥有的任务，归属不匹配时返回空。"""

        return self._session.scalar(select(VideoTask).where(VideoTask.id == task_id, VideoTask.user_id == user_id))

    def get_for_update(self, *, task_id: UUID) -> VideoTask | None:
        """以行锁读取任务，供结算、取消和终态裁决串行执行。"""

        return self._session.scalar(select(VideoTask).where(VideoTask.id == task_id).with_for_update())

    def set_local_result(
        self, *, task: VideoTask, relative_path: str, content_type: str, size_bytes: int, expires_at: datetime
    ) -> None:
        task.local_result_path = relative_path
        task.local_result_content_type = content_type
        task.local_result_size_bytes = size_bytes
        task.result_public_expires_at = expires_at

    def clear_local_result(self, *, task: VideoTask) -> None:
        task.local_result_path = None
        task.local_result_content_type = None
        task.local_result_size_bytes = None
        task.result_public_expires_at = None

    def add_event(self, event: TaskEvent) -> None:
        """追加任务审计事件至当前事务，不提交事务。"""

        self._session.add(event)

    def has_unfinished_tasks(self) -> bool:
        return (
            self._session.scalar(
                select(VideoTask.id)
                .where(
                    VideoTask.status.in_(
                        [
                            VideoTaskStatus.submission_unknown,
                            VideoTaskStatus.queued,
                            VideoTaskStatus.processing,
                        ]
                    )
                )
                .limit(1)
            )
            is not None
        )

    def list_pollable(self, *, limit: int) -> list[VideoTask]:
        return list(
            self._session.scalars(
                select(VideoTask)
                .where(
                    VideoTask.status.in_(
                        [
                            VideoTaskStatus.submission_unknown,
                            VideoTaskStatus.queued,
                            VideoTaskStatus.processing,
                        ]
                    )
                )
                .order_by(VideoTask.created_at)
                .limit(limit)
            )
        )

    def list_created_before_with_statuses(
        self, *, statuses: list[VideoTaskStatus], created_before: datetime, limit: int
    ) -> list[VideoTask]:
        return list(
            self._session.scalars(
                select(VideoTask)
                .where(VideoTask.status.in_(statuses), VideoTask.created_at <= created_before)
                .order_by(VideoTask.created_at)
                .limit(limit)
            )
        )
