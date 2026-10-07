import asyncio
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.core.errors import NotFoundError, ValidationError, error_context
from app.modules.channels.application.concurrency import release_task_concurrency
from app.modules.channels.crud.channels import ChannelCrud
from app.modules.providers.contracts import CreateVideoCommand, ProviderError, ProviderTaskStatus
from app.modules.usage.application.services import UsageApplicationService
from app.modules.video.application.contracts import VideoContentSource
from app.modules.video.application.materials.metering import safe_material_path
from app.modules.video.application.materials.normalization import normalize_video_materials
from app.modules.video.application.tasks.creation import (
    _create_video_task,
    _delivers_external_result,
    _get_frozen_channel_provider,
    _provider_error_details,
    _public_task_response_payload,
    _settle_polled_task,
    _terminate_task_and_release_charge,
    _transition_task,
    to_openai_video_data,
)
from app.modules.video.crud.tasks.async_ import AsyncVideoTaskCrud
from app.modules.video.crud.tasks.sync import VideoTaskCrud
from app.modules.video.model.video_task import VideoTask, VideoTaskStatus
from app.modules.wallet.application.services import WalletApplicationService

_ONDEMAND_REFRESH_STATUSES = frozenset({VideoTaskStatus.queued, VideoTaskStatus.processing})
"""读请求可以自行补一次上游查询的任务状态。

提交结果未知的任务涉及资金裁决，必须在维护任务中统一处理，读请求不参与。
"""

_ONDEMAND_QUERY_TIMEOUT_SECONDS = 10.0
"""读请求内补查上游状态的等待上限，超时即按本地快照返回，避免读接口被上游阻塞。"""


class AsyncVideoApplicationService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def create_openai_video(
        self,
        *,
        user_id: UUID,
        group_ids: list[int],
        access_token_id: UUID,
        token_display_name: str | None,
        request: dict,
        public_base_url: str,
        uploaded_files: dict | None = None,
    ):
        uploaded_files = uploaded_files or {}
        try:
            async with self._session_factory() as session:
                material_fields = await session.run_sync(self._get_material_fields, request)
            normalized_materials = await normalize_video_materials(
                request,
                material_fields=material_fields,
                uploaded_files=uploaded_files,
                public_base_url=public_base_url,
            )
        except ValueError as exc:
            raise ValidationError(str(exc), **error_context(exc)) from exc
        async with self._session_factory() as session:
            task_id, should_submit = await session.run_sync(
                self._create_locally,
                user_id,
                group_ids,
                access_token_id,
                token_display_name,
                normalized_materials.request,
                normalized_materials.facts,
                normalized_materials.materials,
            )
        if should_submit:
            await self._submit(task_id)
        async with self._session_factory() as session:
            task = await AsyncVideoTaskCrud(session).get(task_id=task_id)
            if task is None:
                raise NotFoundError("视频任务不存在")
            balance = await session.run_sync(self._get_wallet_balance, user_id)
            return to_openai_video_data(
                task,
                result_url=self._public_result_url(task, public_base_url=public_base_url),
                balance=balance,
            )

    @staticmethod
    def _get_material_fields(sync_session, request: dict) -> dict:
        model_name = request.get("model")
        if not isinstance(model_name, str):
            raise ValueError("model 必须是字符串")
        model = ChannelCrud(sync_session).get_active_model(name=model_name, model_type="video")
        if model is None:
            raise ValueError("未配置当前公开模型")
        contract = model.input_contract
        if not isinstance(contract, dict):
            raise ValueError("视频模型缺少请求契约")
        material_fields = contract.get("materials", {})
        if not isinstance(material_fields, dict):
            raise ValueError("视频模型素材契约不合法")
        return material_fields

    @staticmethod
    def _create_locally(
        sync_session, user_id, group_ids, access_token_id, token_display_name, request, facts, materials
    ):
        try:
            task = _create_video_task(
                sync_session,
                user_id=user_id,
                group_ids=group_ids,
                access_token_id=access_token_id,
                token_display_name=token_display_name,
                request=request,
                material_facts=facts,
                input_materials=materials,
            )
            sync_session.commit()
            return task.id, task.status == VideoTaskStatus.submitting
        except ValueError as exc:
            sync_session.rollback()
            raise ValidationError(str(exc), **error_context(exc)) from exc
        except Exception:
            sync_session.rollback()
            raise

    @staticmethod
    def _get_wallet_balance(sync_session, user_id: UUID) -> str:
        wallet = WalletApplicationService(sync_session).get_wallet_by_user_id(user_id)
        if wallet is None:
            raise NotFoundError("用户钱包不存在")
        return str(wallet.balance)

    async def get_owned_openai_video(self, *, video_id: UUID, user_id: UUID, public_base_url: str):
        task = await self._get_owned_task_with_refresh(video_id=video_id, user_id=user_id)
        async with self._session_factory() as session:
            balance = await session.run_sync(self._get_wallet_balance, user_id)
        return to_openai_video_data(
            task,
            result_url=self._public_result_url(task, public_base_url=public_base_url),
            balance=balance,
        )

    async def get_owned_video_content(self, *, video_id: UUID, user_id: UUID, variant: str) -> VideoContentSource:
        if variant != "video":
            raise ValidationError("当前视频不支持该成品类型")
        task = await self._get_owned_task_with_refresh(video_id=video_id, user_id=user_id)
        if task.status != VideoTaskStatus.succeeded:
            raise ValidationError("视频成品尚不可下载")
        if _delivers_external_result(task):
            return await self._relay_external_result(task)
        if self._ready_local_result(task) is not None:
            return self._local_content_source(task)
        return self._local_content_source(await self._localize_on_demand(task_id=video_id))

    async def get_public_video_content(self, *, task_id: UUID) -> VideoContentSource:
        async with self._session_factory() as session:
            task = await AsyncVideoTaskCrud(session).get(task_id=task_id)
            if task is None:
                raise NotFoundError("视频任务不存在")
            if not _delivers_external_result(task):
                return self._local_content_source(task)
            if not isinstance(task.result_url, str) or not task.result_url:
                raise NotFoundError("视频任务不存在")
            return VideoContentSource(redirect_url=task.result_url)

    async def _relay_external_result(self, task: VideoTask) -> VideoContentSource:
        """外部直链交付的成品由平台反代上游地址，使鉴权下载接口仍返回字节流。"""

        try:
            async with self._session_factory() as session:
                provider, upstream_task_id = await session.run_sync(self._load_provider, task.id)
            chunks, content_type = await provider.fetch_result(upstream_task_id)
        except ProviderError as exc:
            raise ValidationError("视频成品尚不可下载") from exc
        return VideoContentSource(content_type=content_type, chunks=chunks)

    @classmethod
    def _local_content_source(cls, task: VideoTask) -> VideoContentSource:
        """平台本地化的成品按本地文件流式下发。"""

        try:
            chunks, content_type = cls._local_result_stream(task)
        except NotFoundError as exc:
            raise ValidationError("视频成品尚不可下载") from exc
        return VideoContentSource(content_type=content_type, chunks=chunks)

    async def _get_owned_task_with_refresh(self, *, video_id: UUID, user_id: UUID) -> VideoTask:
        """读取归属任务，并对处理中的任务补一次上游查询，让读请求尽量拿到最新状态。

        上游出片通常只需数秒，若完全依赖维护任务轮询，读请求会在一个调度周期内持续返回过期状态；
        补查失败或超时都不影响本地快照返回。
        """

        async with self._session_factory() as session:
            task = await AsyncVideoTaskCrud(session).get_owned(task_id=video_id, user_id=user_id)
            if task is None:
                raise NotFoundError("视频任务不存在")
            if task.status not in _ONDEMAND_REFRESH_STATUSES:
                return task
        await self._refresh_task_status_on_demand(task_id=video_id)
        async with self._session_factory() as session:
            refreshed = await AsyncVideoTaskCrud(session).get_owned(task_id=video_id, user_id=user_id)
            if refreshed is None:
                raise NotFoundError("视频任务不存在")
            return refreshed

    async def _refresh_task_status_on_demand(self, *, task_id: UUID) -> None:
        """按需补一次上游状态查询，并复用维护任务的轮询结果写入逻辑。"""

        async with self._session_factory() as session:
            source = await session.run_sync(self._load_ondemand_refresh_source, task_id)
        if source is None:
            return
        provider, upstream_task_id = source
        try:
            snapshot = await asyncio.wait_for(provider.query(upstream_task_id), timeout=_ONDEMAND_QUERY_TIMEOUT_SECONDS)
        except (ProviderError, TimeoutError):
            return
        async with self._session_factory() as session:
            await session.run_sync(self._apply_poll_result, task_id, snapshot)

    @staticmethod
    def _load_ondemand_refresh_source(sync_session, task_id: UUID):
        """取出补查上游所需的 Provider 与上游任务标识；任务不满足补查条件时返回空值。"""

        task = VideoTaskCrud(sync_session).get(task_id=task_id)
        if task is None or task.status not in _ONDEMAND_REFRESH_STATUSES or not task.upstream_task_id:
            return None
        return _get_frozen_channel_provider(sync_session, task=task), task.upstream_task_id

    async def _localize_on_demand(self, *, task_id: UUID) -> VideoTask:
        """在读请求内补做一次成品本地化，下载失败仍按维护任务的记账方式处理。"""

        try:
            await self._localize_task(task_id=task_id)
        except ProviderError as exc:
            async with self._session_factory() as session:
                await session.run_sync(self._record_localization_failure, task_id, exc)
            raise ValidationError("视频成品尚不可下载") from exc
        async with self._session_factory() as session:
            task = await AsyncVideoTaskCrud(session).get(task_id=task_id)
            if task is None:
                raise NotFoundError("视频任务不存在")
            return task

    async def get_material_content(self, *, resource_id: str) -> tuple[AsyncIterator[bytes], str]:
        path = safe_material_path(resource_id)
        if not path.is_file():
            raise NotFoundError("素材不存在")
        return self._iter_file(path), "application/octet-stream"

    async def _submit(self, task_id: UUID) -> None:
        async with self._session_factory() as session:
            provider, command = await session.run_sync(self._load_submission, task_id)
        try:
            submission = await provider.submit(command)
        except ProviderError as exc:
            await self._record_submission_error(task_id, exc)
            return
        async with self._session_factory() as session:
            await session.run_sync(self._record_submission, task_id, submission)

    @staticmethod
    def _load_provider(sync_session, task_id: UUID):
        task = VideoTaskCrud(sync_session).get(task_id=task_id)
        if task is None:
            raise NotFoundError("视频任务不存在")
        return _get_frozen_channel_provider(sync_session, task=task), task.upstream_task_id

    @staticmethod
    def _load_submission(sync_session, task_id: UUID):
        task = VideoTaskCrud(sync_session).get(task_id=task_id)
        if task is None:
            raise NotFoundError("视频任务不存在")
        return _get_frozen_channel_provider(sync_session, task=task), CreateVideoCommand(
            str(task.id), task.execution_snapshot["provider_request"]
        )

    @staticmethod
    def _record_submission(sync_session, task_id: UUID, submission) -> None:
        """写入提交结果；同步 Provider 已出成品时在同一事务内直接结算，无需等待轮询。"""

        try:
            task = VideoTaskCrud(sync_session).get_for_update(task_id=task_id)
            if task is None or task.status != VideoTaskStatus.submitting:
                sync_session.rollback()
                return
            task.upstream_task_id = submission.upstream_task_id
            task.submission_response = submission.raw
            task.submitted_at = datetime.now(UTC)
            if submission.status is ProviderTaskStatus.succeeded:
                _transition_task(
                    sync_session, task=task, target=VideoTaskStatus.queued, event_type="provider_submitted"
                )
                _settle_polled_task(
                    sync_session,
                    task=task,
                    result_url=submission.result_url,
                    result_payload=submission.raw,
                )
            else:
                _transition_task(
                    sync_session,
                    task=task,
                    target=VideoTaskStatus.processing
                    if submission.status.value == "processing"
                    else VideoTaskStatus.queued,
                    event_type="provider_submitted",
                )
            UsageApplicationService(sync_session).update_resource_response(
                resource_type="video_task",
                resource_id=task.id,
                public_response_payload=_public_task_response_payload(task),
                upstream_response_payload=submission.raw,
            )
            sync_session.commit()
        except Exception:
            sync_session.rollback()
            raise

    async def _record_submission_error(self, task_id: UUID, exc: ProviderError) -> None:
        async with self._session_factory() as session:
            await session.run_sync(self._apply_submission_error, task_id, exc)

    @staticmethod
    def _apply_submission_error(sync_session, task_id: UUID, exc: ProviderError) -> None:
        try:
            task = VideoTaskCrud(sync_session).get_for_update(task_id=task_id)
            if task is None or task.status != VideoTaskStatus.submitting:
                sync_session.rollback()
                return
            error_code, error_message = _provider_error_details(
                exc.response_body,
                fallback_code=exc.code,
                fallback_message=str(exc),
            )
            _terminate_task_and_release_charge(
                sync_session,
                task=task,
                target=VideoTaskStatus.failed,
                event_type="provider_submit_failed",
                error_code=error_code,
                error_message=error_message,
                upstream_response_payload=exc.response_body,
            )
            sync_session.commit()
        except Exception:
            sync_session.rollback()
            raise

    async def poll_once(self) -> dict[str, int]:
        result = {
            "scanned": 0,
            "updated": 0,
            "settled_historical": 0,
            "localized": 0,
            "localization_errors": 0,
            "expired_deleted": 0,
            "errors": 0,
        }
        async with self._session_factory() as session:
            historical_task_ids = await AsyncVideoTaskCrud(session).list_succeeded_with_reserved_usage_ids(limit=100)
        for task_id in historical_task_ids:
            try:
                async with self._session_factory() as session:
                    settled = await session.run_sync(self._settle_historical_usage, task_id)
                result["settled_historical"] += int(settled)
            except Exception:
                result["errors"] += 1
        settings = get_settings()
        async with self._session_factory() as session:
            timeout_task_ids = await AsyncVideoTaskCrud(session).list_submitted_before_with_statuses(
                statuses=[VideoTaskStatus.queued, VideoTaskStatus.processing],
                submitted_before=datetime.now(UTC) - timedelta(seconds=settings.video_task_timeout_seconds),
                limit=settings.video_maintenance_batch_size,
            )
        for task_id in timeout_task_ids:
            try:
                async with self._session_factory() as session:
                    timed_out = await session.run_sync(self._apply_business_timeout, task_id)
                result["updated"] += int(timed_out)
            except Exception:
                result["errors"] += 1
        async with self._session_factory() as session:
            # 与读请求共用最近查询时间：一个调度周期内已查过上游的任务本轮不再重复查询
            polled_before = datetime.now(UTC) - timedelta(seconds=settings.system_task_scheduler_interval_seconds)
            task_ids = await AsyncVideoTaskCrud(session).list_pollable_ids(
                limit=settings.video_maintenance_batch_size, polled_before=polled_before
            )
        for task_id in task_ids:
            result["scanned"] += 1
            try:
                async with self._session_factory() as session:
                    task = await AsyncVideoTaskCrud(session).get(task_id=task_id)
                    if task is None:
                        continue
                    if task.status == VideoTaskStatus.submission_unknown:
                        updated = await session.run_sync(self._terminate_unknown_submission, task_id)
                        result["updated"] += int(updated)
                        continue
                    if task.status not in {VideoTaskStatus.queued, VideoTaskStatus.processing}:
                        continue
                    if not task.upstream_task_id:
                        continue
                    provider, upstream_task_id = await session.run_sync(self._load_provider, task_id)
                snapshot = await provider.query(upstream_task_id)
                async with self._session_factory() as session:
                    updated = await session.run_sync(self._apply_poll_result, task_id, snapshot)
                result["updated"] += int(updated)
            except Exception:
                result["errors"] += 1
        async with self._session_factory() as session:
            localize_ids = await AsyncVideoTaskCrud(session).list_succeeded_without_local_result_ids(
                limit=get_settings().video_maintenance_batch_size
            )
            expired_ids = await AsyncVideoTaskCrud(session).list_expired_local_result_ids(
                expires_before=datetime.now(UTC), limit=get_settings().video_maintenance_batch_size
            )
        for task_id in localize_ids:
            try:
                await self._localize_task(task_id=task_id)
                result["localized"] += 1
            except Exception as exc:
                async with self._session_factory() as session:
                    failed = await session.run_sync(self._record_localization_failure, task_id, exc)
                result["localization_errors"] += 1
                result["updated"] += int(failed)
        for task_id in expired_ids:
            try:
                await self._cleanup_local_result(task_id=task_id)
                result["expired_deleted"] += 1
            except Exception:
                result["errors"] += 1
        return result

    async def _localize_task(self, *, task_id: UUID) -> None:
        async with self._session_factory() as session:
            source = await session.run_sync(self._load_localization_source, task_id)
        if source is None:
            return
        provider, upstream_task_id = source
        chunks, content_type = await provider.fetch_result(upstream_task_id)
        relative_path = f"{task_id}.mp4"
        target = self._safe_result_path(relative_path)
        # 临时文件按次命名：读请求与维护任务可能同时为同一任务落盘，共用临时名会互相截断
        temporary = target.parent / f"{target.name}.{uuid4().hex}.tmp"
        size_bytes = 0
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with temporary.open("wb") as output:
                async for chunk in chunks:
                    output.write(chunk)
                    size_bytes += len(chunk)
            os.replace(temporary, target)
            async with self._session_factory() as session:
                await session.run_sync(
                    self._persist_local_result,
                    task_id,
                    relative_path,
                    content_type,
                    size_bytes,
                )
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

    @staticmethod
    def _record_localization_failure(sync_session, task_id: UUID, exc: Exception) -> bool:
        try:
            task = VideoTaskCrud(sync_session).get_for_update(task_id=task_id)
            if task is None or task.status != VideoTaskStatus.succeeded or task.local_result_path:
                sync_session.rollback()
                return False
            now = datetime.now(UTC)
            if task.result_download_failed_at is None:
                task.result_download_failed_at = now
                sync_session.commit()
                return False
            if now - task.result_download_failed_at < timedelta(
                seconds=get_settings().video_result_download_retry_seconds
            ):
                sync_session.commit()
                return False
            response_payload = exc.response_body if isinstance(exc, ProviderError) else None
            task.error_payload = {
                "code": "result_download_failed",
                "message": "视频成品下载失败，请重新创建任务",
            }
            _transition_task(
                sync_session,
                task=task,
                target=VideoTaskStatus.failed,
                event_type="result_download_retry_expired",
                payload=task.error_payload,
            )
            UsageApplicationService(sync_session).reverse_settled_resource(
                resource_type="video_task",
                resource_id=task.id,
                reason="视频成品下载失败退款",
                public_response_payload=_public_task_response_payload(task),
                upstream_response_payload=response_payload,
            )
            sync_session.commit()
            return True
        except Exception:
            sync_session.rollback()
            raise

    @staticmethod
    def _load_localization_source(sync_session, task_id: UUID):
        task = VideoTaskCrud(sync_session).get(task_id=task_id)
        if (
            task is None
            or task.status != VideoTaskStatus.succeeded
            or task.local_result_path
            or not task.upstream_task_id
            or _delivers_external_result(task)
        ):
            return None
        return _get_frozen_channel_provider(sync_session, task=task), task.upstream_task_id

    @staticmethod
    def _persist_local_result(
        sync_session, task_id: UUID, relative_path: str, content_type: str, size_bytes: int
    ) -> None:
        try:
            task = VideoTaskCrud(sync_session).get_for_update(task_id=task_id)
            if task is not None and task.status == VideoTaskStatus.succeeded and task.local_result_path is None:
                VideoTaskCrud(sync_session).set_local_result(
                    task=task,
                    relative_path=relative_path,
                    content_type=content_type,
                    size_bytes=size_bytes,
                    expires_at=datetime.now(UTC) + timedelta(hours=get_settings().video_result_retention_hours),
                )
                result_url = AsyncVideoApplicationService._public_result_url(
                    task, public_base_url=get_settings().public_base_url
                )
                if result_url is not None:
                    UsageApplicationService(sync_session).set_resource_result_url(
                        resource_type="video_task", resource_id=task.id, result_url=result_url
                    )
                sync_session.commit()
                return
            sync_session.rollback()
        except Exception:
            sync_session.rollback()
            raise

    async def _cleanup_local_result(self, *, task_id: UUID) -> None:
        async with self._session_factory() as session:
            relative_path = await session.run_sync(self._get_expired_local_result_path, task_id)
        if relative_path is not None:
            self._safe_result_path(relative_path).unlink(missing_ok=True)
            async with self._session_factory() as session:
                await session.run_sync(self._clear_local_result, task_id)

    @staticmethod
    def _get_expired_local_result_path(sync_session, task_id: UUID) -> str | None:
        task = VideoTaskCrud(sync_session).get(task_id=task_id)
        if task is None or not task.local_result_path or not task.result_public_expires_at:
            return None
        if task.result_public_expires_at > datetime.now(UTC):
            return None
        return task.local_result_path

    @staticmethod
    def _clear_local_result(sync_session, task_id: UUID) -> None:
        try:
            task = VideoTaskCrud(sync_session).get_for_update(task_id=task_id)
            if task is None or not task.local_result_path or not task.result_public_expires_at:
                sync_session.rollback()
                return
            if task.result_public_expires_at > datetime.now(UTC):
                sync_session.rollback()
                return
            VideoTaskCrud(sync_session).clear_local_result(task=task)
            sync_session.commit()
        except Exception:
            sync_session.rollback()
            raise

    @staticmethod
    def _safe_result_path(relative_path: str) -> Path:
        root = get_settings().video_result_storage_dir.resolve()
        path = (root / relative_path).resolve()
        if root not in path.parents or path == root:
            raise NotFoundError("视频任务不存在")
        return path

    @staticmethod
    def _ready_local_result(task: VideoTask) -> tuple[str, str] | None:
        """返回可直接下发的本地成品（相对路径、内容类型）；未落盘或已过公开期时返回空值。"""

        expires_at = task.result_public_expires_at
        if (
            task.status != VideoTaskStatus.succeeded
            or not task.local_result_path
            or not task.local_result_content_type
            or expires_at is None
            or expires_at <= datetime.now(UTC)
        ):
            return None
        return task.local_result_path, task.local_result_content_type

    @classmethod
    def _local_result_stream(cls, task: VideoTask) -> tuple[AsyncIterator[bytes], str]:
        ready = cls._ready_local_result(task)
        if ready is None:
            raise NotFoundError("视频任务不存在")
        relative_path, content_type = ready
        path = cls._safe_result_path(relative_path)
        if not path.is_file():
            raise NotFoundError("视频任务不存在")
        return cls._iter_file(path), content_type

    @staticmethod
    async def _iter_file(path: Path) -> AsyncIterator[bytes]:
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                yield chunk

    @staticmethod
    def _public_result_url(task: VideoTask, *, public_base_url: str) -> str | None:
        """外部直链交付的任务直接对外给出上游地址，其余任务在本地成品可用时给出平台下载地址。"""

        if _delivers_external_result(task):
            return task.result_url
        try:
            AsyncVideoApplicationService._local_result_stream(task)
        except NotFoundError:
            return None
        return f"{public_base_url.rstrip('/')}/v1/videos/public/task_{task.id}"

    @staticmethod
    def _apply_business_timeout(sync_session, task_id: UUID) -> bool:
        try:
            task = VideoTaskCrud(sync_session).get_for_update(task_id=task_id)
            if task is None or task.status not in {VideoTaskStatus.queued, VideoTaskStatus.processing}:
                sync_session.rollback()
                return False
            _terminate_task_and_release_charge(
                sync_session,
                task=task,
                target=VideoTaskStatus.timed_out,
                event_type="business_timeout",
                error_code="business_timeout",
                error_message="视频任务超过配置的业务等待时限",
            )
            sync_session.commit()
            return True
        except Exception:
            sync_session.rollback()
            raise

    @staticmethod
    def _terminate_unknown_submission(sync_session, task_id: UUID) -> bool:
        try:
            task = VideoTaskCrud(sync_session).get_for_update(task_id=task_id)
            if task is None or task.status != VideoTaskStatus.submission_unknown:
                sync_session.rollback()
                return False
            _terminate_task_and_release_charge(
                sync_session,
                task=task,
                target=VideoTaskStatus.failed,
                event_type="provider_submit_unknown",
                error_code="provider_submit_unknown",
                error_message="视频任务提交结果未知，任务已终止",
            )
            sync_session.commit()
            return True
        except Exception:
            sync_session.rollback()
            raise

    @staticmethod
    def _apply_poll_result(sync_session, task_id: UUID, snapshot) -> bool:
        """写入一次已完成的上游查询结果，并记录查询时间供轮询任务与读请求共用计时。"""

        try:
            task = VideoTaskCrud(sync_session).get_for_update(task_id=task_id)
            if task is None or task.status not in {VideoTaskStatus.queued, VideoTaskStatus.processing}:
                sync_session.rollback()
                return False
            task.progress = snapshot.progress
            task.result_payload = snapshot.raw
            task.last_polled_at = datetime.now(UTC)
            if snapshot.status.value == "succeeded":
                _settle_polled_task(
                    sync_session, task=task, result_url=snapshot.result_url, result_payload=snapshot.raw
                )
            elif snapshot.status.value in {"failed", "cancelled"}:
                error_code, error_message = _provider_error_details(
                    snapshot.raw,
                    fallback_code=f"provider_{snapshot.status.value}",
                    fallback_message="上游任务未成功完成",
                )
                _terminate_task_and_release_charge(
                    sync_session,
                    task=task,
                    target=VideoTaskStatus(snapshot.status.value),
                    event_type="provider_terminal",
                    error_code=error_code,
                    error_message=error_message,
                    upstream_response_payload=snapshot.raw,
                )
            elif snapshot.status.value == "processing" and task.status == VideoTaskStatus.queued:
                _transition_task(
                    sync_session, task=task, target=VideoTaskStatus.processing, event_type="provider_processing"
                )
                UsageApplicationService(sync_session).update_resource_response(
                    resource_type="video_task",
                    resource_id=task.id,
                    public_response_payload=_public_task_response_payload(task),
                    upstream_response_payload=snapshot.raw,
                )
            sync_session.commit()
            return True
        except Exception:
            sync_session.rollback()
            raise

    @staticmethod
    def _settle_historical_usage(sync_session, task_id: UUID) -> bool:
        try:
            task = VideoTaskCrud(sync_session).get_for_update(task_id=task_id)
            if task is None or task.status != VideoTaskStatus.succeeded:
                sync_session.rollback()
                return False
            usage = UsageApplicationService(sync_session).settle_resource(
                resource_type="video_task",
                resource_id=task.id,
                public_response_payload=_public_task_response_payload(task),
                upstream_response_payload=task.result_payload,
            )
            if usage is None or usage.status.value != "succeeded":
                sync_session.rollback()
                return False
            release_task_concurrency(sync_session, task_id=task.id)
            sync_session.commit()
            return True
        except Exception:
            sync_session.rollback()
            raise
