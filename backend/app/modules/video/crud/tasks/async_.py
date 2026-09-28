from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.usage.model import UsageRecord, UsageRecordStatus
from app.modules.video.model.video_task import (
    RESULT_DELIVERY_EXTERNAL,
    RESULT_DELIVERY_KEY,
    TaskEvent,
    VideoTask,
    VideoTaskStatus,
)


def _requires_local_result():
    """判定任务成品是否仍需平台本地化。

    冻结快照标记为外部直链交付（如同步 Provider）的任务由上游地址直接对外提供，不参与成品下载与落盘维护。
    """

    return VideoTask.execution_snapshot[RESULT_DELIVERY_KEY].astext.is_distinct_from(RESULT_DELIVERY_EXTERNAL)


class AsyncVideoTaskCrud:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, *, task_id: UUID) -> VideoTask | None:
        return await self._session.get(VideoTask, task_id)

    async def get_owned(self, *, task_id: UUID, user_id: UUID) -> VideoTask | None:
        return await self._session.scalar(
            select(VideoTask).where(VideoTask.id == task_id, VideoTask.user_id == user_id)
        )

    async def get_for_update(self, *, task_id: UUID) -> VideoTask | None:
        return await self._session.scalar(select(VideoTask).where(VideoTask.id == task_id).with_for_update())

    async def list_pollable_ids(self, *, limit: int, polled_before: datetime) -> list[UUID]:
        """列出待轮询任务，并跳过最近刚查询过上游的任务。

        ``polled_before`` 为"最近一次查询时间"的下界：轮询任务与读请求共用 ``last_polled_at``，
        因此读请求刚触发的查询会让该任务推迟到下一轮，避免同一周期内重复查询上游。
        """

        rows = await self._session.scalars(
            select(VideoTask.id)
            .where(
                VideoTask.status.in_(
                    [
                        VideoTaskStatus.submission_unknown,
                        VideoTaskStatus.queued,
                        VideoTaskStatus.processing,
                    ]
                ),
                (VideoTask.last_polled_at.is_(None)) | (VideoTask.last_polled_at <= polled_before),
            )
            .order_by(VideoTask.created_at)
            .limit(limit)
        )
        return list(rows)

    async def list_succeeded_with_reserved_usage_ids(self, *, limit: int) -> list[UUID]:
        rows = await self._session.scalars(
            select(VideoTask.id)
            .join(
                UsageRecord,
                (UsageRecord.resource_type == "video_task") & (UsageRecord.resource_id == VideoTask.id),
            )
            .where(VideoTask.status == VideoTaskStatus.succeeded, UsageRecord.status == UsageRecordStatus.reserved)
            .order_by(VideoTask.completed_at, VideoTask.id)
            .limit(limit)
        )
        return list(rows)

    async def list_succeeded_without_local_result_ids(self, *, limit: int) -> list[UUID]:
        rows = await self._session.scalars(
            select(VideoTask.id)
            .where(
                VideoTask.status == VideoTaskStatus.succeeded,
                VideoTask.upstream_task_id.is_not(None),
                VideoTask.local_result_path.is_(None),
                _requires_local_result(),
            )
            .order_by(VideoTask.completed_at, VideoTask.id)
            .limit(limit)
        )
        return list(rows)

    async def list_expired_local_result_ids(self, *, expires_before: datetime, limit: int) -> list[UUID]:
        rows = await self._session.scalars(
            select(VideoTask.id)
            .where(
                VideoTask.local_result_path.is_not(None),
                VideoTask.result_public_expires_at.is_not(None),
                VideoTask.result_public_expires_at <= expires_before,
            )
            .order_by(VideoTask.result_public_expires_at, VideoTask.id)
            .limit(limit)
        )
        return list(rows)

    async def has_local_result_maintenance_candidates(self, *, expires_before: datetime) -> bool:
        return (
            await self._session.scalar(
                select(VideoTask.id)
                .where(
                    (
                        (VideoTask.status == VideoTaskStatus.succeeded)
                        & VideoTask.local_result_path.is_(None)
                        & _requires_local_result()
                    )
                    | (
                        VideoTask.local_result_path.is_not(None)
                        & VideoTask.result_public_expires_at.is_not(None)
                        & (VideoTask.result_public_expires_at <= expires_before)
                    )
                )
                .limit(1)
            )
        ) is not None

    async def has_succeeded_task_with_reserved_usage(self) -> bool:
        return (
            await self._session.scalar(
                select(VideoTask.id)
                .join(
                    UsageRecord,
                    (UsageRecord.resource_type == "video_task") & (UsageRecord.resource_id == VideoTask.id),
                )
                .where(VideoTask.status == VideoTaskStatus.succeeded, UsageRecord.status == UsageRecordStatus.reserved)
                .limit(1)
            )
        ) is not None

    async def list_submitted_before_with_statuses(
        self, *, statuses: list[VideoTaskStatus], submitted_before: datetime, limit: int
    ) -> list[UUID]:
        rows = await self._session.scalars(
            select(VideoTask.id)
            .where(
                VideoTask.status.in_(statuses),
                VideoTask.submitted_at.is_not(None),
                VideoTask.submitted_at <= submitted_before,
            )
            .order_by(VideoTask.submitted_at, VideoTask.id)
            .limit(limit)
        )
        return list(rows)

    async def has_unfinished_tasks(self) -> bool:
        return (
            await self._session.scalar(
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
        ) is not None

    def add_event(self, event: TaskEvent) -> None:
        self._session.add(event)
