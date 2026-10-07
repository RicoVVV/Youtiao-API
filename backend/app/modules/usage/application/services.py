"""使用记录应用服务，协调调用审计与钱包余额变化。"""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from app.core.errors import NotFoundError, ValidationError
from app.modules.usage.crud.usage_record_crud import UsageRecordCrud
from app.modules.usage.model import UsageRecord, UsageRecordStatus
from app.modules.wallet.application.services import WalletApplicationService
from sqlmodel import Session


class UsageApplicationService:
    def __init__(self, session: Session) -> None:
        self._crud = UsageRecordCrud(session)
        self._wallet = WalletApplicationService(session)

    def create_reserved(
        self,
        *,
        user_id: UUID,
        access_token_id: UUID | None,
        token_display_name: str | None,
        token_group_id: int | None,
        request_id: str,
        request_type: str,
        resource_type: str | None,
        resource_id: UUID | None,
        model_id: UUID | None,
        model_name: str,
        channel_id: UUID | None,
        channel_name: str | None,
        provider_name: str,
        request_payload: dict,
        amount: Decimal,
        reason: str,
        response_metadata: dict | None = None,
    ) -> UsageRecord:
        if amount <= 0:
            raise ValidationError("扣费金额必须为正数")
        record = self._crud.create(
            UsageRecord(
                user_id=user_id,
                access_token_id=access_token_id,
                token_display_name=token_display_name,
                token_group_id=token_group_id,
                request_id=request_id,
                request_type=request_type,
                resource_type=resource_type,
                resource_id=resource_id,
                model_id=model_id,
                model_name=model_name,
                channel_id=channel_id,
                channel_name=channel_name,
                provider_name=provider_name,
                request_payload=dict(request_payload),
                amount=amount,
                response_metadata=dict(response_metadata) if response_metadata is not None else None,
            )
        )
        self._wallet.reserve_usage_balance(user_id=user_id, usage_record_id=record.id, amount=amount, reason=reason)
        return record

    def create_settled_postpaid(
        self,
        *,
        user_id: UUID,
        access_token_id: UUID | None,
        token_display_name: str | None,
        token_group_id: int | None,
        request_id: str,
        request_type: str,
        resource_type: str | None,
        resource_id: UUID | None,
        model_id: UUID | None,
        model_name: str,
        channel_id: UUID | None,
        channel_name: str | None,
        provider_name: str,
        request_payload: dict,
        amount: Decimal,
        reason: str,
        response_metadata: dict | None = None,
        public_response_payload: dict | None = None,
        upstream_response_payload: dict | None = None,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        cached_tokens: int | None = None,
        cache_write_tokens: int | None = None,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        duration_ms: int | None = None,
        first_token_duration_ms: int | None = None,
    ) -> UsageRecord:
        """按实际用量直接落一条已结算使用记录，并后付费扣减钱包余额。

        与预占模式不同，本方法不预留资金；余额不足时按业务约定允许扣成负数表示欠费。
        """

        if amount <= 0:
            raise ValidationError("扣费金额必须为正数")
        now = datetime.now(UTC)
        record = self._crud.create(
            UsageRecord(
                user_id=user_id,
                access_token_id=access_token_id,
                token_display_name=token_display_name,
                token_group_id=token_group_id,
                request_id=request_id,
                request_type=request_type,
                resource_type=resource_type,
                resource_id=resource_id,
                model_id=model_id,
                model_name=model_name,
                channel_id=channel_id,
                channel_name=channel_name,
                provider_name=provider_name,
                request_payload=dict(request_payload),
                amount=amount,
                status=UsageRecordStatus.succeeded,
                started_at=started_at or now,
                completed_at=completed_at or now,
                duration_ms=duration_ms,
                first_token_duration_ms=first_token_duration_ms,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cached_tokens=cached_tokens,
                cache_write_tokens=cache_write_tokens,
                response_metadata=dict(response_metadata) if response_metadata is not None else None,
                public_response_payload=dict(public_response_payload) if public_response_payload is not None else None,
                upstream_response_payload=(
                    dict(upstream_response_payload) if upstream_response_payload is not None else None
                ),
            )
        )
        self._wallet.charge_usage_balance(user_id=user_id, usage_record_id=record.id, amount=amount, reason=reason)
        return record

    def create_failed_postpaid(
        self,
        *,
        user_id: UUID,
        access_token_id: UUID | None,
        token_display_name: str | None,
        token_group_id: int | None,
        request_id: str,
        request_type: str,
        resource_type: str | None,
        resource_id: UUID | None,
        model_id: UUID | None,
        model_name: str,
        channel_id: UUID | None,
        channel_name: str | None,
        provider_name: str,
        request_payload: dict,
        response_metadata: dict | None = None,
        upstream_response_payload: dict | None = None,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        duration_ms: int | None = None,
        first_token_duration_ms: int | None = None,
    ) -> UsageRecord:
        now = datetime.now(UTC)
        return self._crud.create(
            UsageRecord(
                user_id=user_id,
                access_token_id=access_token_id,
                token_display_name=token_display_name,
                token_group_id=token_group_id,
                request_id=request_id,
                request_type=request_type,
                resource_type=resource_type,
                resource_id=resource_id,
                model_id=model_id,
                model_name=model_name,
                channel_id=channel_id,
                channel_name=channel_name,
                provider_name=provider_name,
                request_payload=dict(request_payload),
                amount=Decimal(0),
                status=UsageRecordStatus.failed,
                started_at=started_at or now,
                completed_at=completed_at or now,
                duration_ms=duration_ms,
                first_token_duration_ms=first_token_duration_ms,
                response_metadata=dict(response_metadata) if response_metadata is not None else None,
                upstream_response_payload=(
                    dict(upstream_response_payload) if upstream_response_payload is not None else None
                ),
            )
        )

    def create_channel_test_result(
        self,
        *,
        user_id: UUID,
        request_id: str,
        model_id: UUID,
        model_name: str,
        channel_id: UUID,
        channel_name: str,
        provider_name: str,
        request_payload: dict,
        response_metadata: dict,
        amount: Decimal,
        duration_ms: int,
        succeeded: bool,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        cached_tokens: int | None = None,
        cache_write_tokens: int | None = None,
    ) -> UsageRecord:
        now = datetime.now(UTC)
        record = self._crud.create(
            UsageRecord(
                user_id=user_id,
                access_token_id=None,
                token_display_name=None,
                token_group_id=None,
                request_id=request_id,
                request_type="channel_test",
                resource_type=None,
                resource_id=None,
                model_id=model_id,
                model_name=model_name,
                channel_id=channel_id,
                channel_name=channel_name,
                provider_name=provider_name,
                request_payload=dict(request_payload),
                response_metadata=dict(response_metadata),
                amount=amount,
                status=UsageRecordStatus.succeeded if succeeded else UsageRecordStatus.failed,
                started_at=now,
                completed_at=now,
                duration_ms=duration_ms,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cached_tokens=cached_tokens,
                cache_write_tokens=cache_write_tokens,
            )
        )
        if succeeded and amount > 0:
            self._wallet.charge_usage_balance(
                user_id=user_id,
                usage_record_id=record.id,
                amount=amount,
                reason="渠道测试调用扣费",
            )
        return record

    def settle_resource(
        self,
        *,
        resource_type: str,
        resource_id: UUID,
        public_response_payload: dict | None = None,
        upstream_response_payload: dict | None = None,
    ) -> UsageRecord | None:
        record = self._crud.get_for_resource_update(resource_type=resource_type, resource_id=resource_id)
        if record is not None and record.status == UsageRecordStatus.reserved:
            now = datetime.now(UTC)
            record.status = UsageRecordStatus.succeeded
            record.completed_at = now
            record.public_response_payload = (
                dict(public_response_payload) if public_response_payload is not None else None
            )
            record.upstream_response_payload = (
                dict(upstream_response_payload) if upstream_response_payload is not None else None
            )
            if record.started_at is not None:
                record.duration_ms = int((now - record.started_at).total_seconds() * 1000)
        return record

    def update_resource_response(
        self,
        *,
        resource_type: str,
        resource_id: UUID,
        public_response_payload: dict | None = None,
        upstream_response_payload: dict | None = None,
    ) -> UsageRecord | None:
        """在资源仍为预占态时刷新其最新响应快照，使使用记录随任务状态变更保持同步。"""

        record = self._crud.get_for_resource_update(resource_type=resource_type, resource_id=resource_id)
        if record is None or record.status != UsageRecordStatus.reserved:
            return record
        if public_response_payload is not None:
            record.public_response_payload = dict(public_response_payload)
        if upstream_response_payload is not None:
            record.upstream_response_payload = dict(upstream_response_payload)
        return record

    def set_resource_result_url(
        self,
        *,
        resource_type: str,
        resource_id: UUID,
        result_url: str,
    ) -> UsageRecord | None:
        """在资源成品落地后，将公开下载地址写入使用记录响应快照。"""

        record = self._crud.get_for_resource_update(resource_type=resource_type, resource_id=resource_id)
        if record is None or not isinstance(record.public_response_payload, dict):
            return record
        payload = dict(record.public_response_payload)
        if payload.get("result_url") == result_url:
            return record
        payload["result_url"] = result_url
        record.public_response_payload = payload
        return record

    def refund_resource(
        self,
        *,
        resource_type: str,
        resource_id: UUID,
        reason: str,
        public_response_payload: dict | None = None,
        upstream_response_payload: dict | None = None,
    ) -> UsageRecord | None:
        record = self._crud.get_for_resource_update(resource_type=resource_type, resource_id=resource_id)
        if record is None or record.status != UsageRecordStatus.reserved:
            return record
        self._wallet.refund_usage_balance(
            user_id=record.user_id, usage_record_id=record.id, amount=record.amount, reason=reason
        )
        now = datetime.now(UTC)
        record.status = UsageRecordStatus.refunded
        record.completed_at = now
        if record.started_at is not None:
            record.duration_ms = int((now - record.started_at).total_seconds() * 1000)
        if public_response_payload is not None:
            record.public_response_payload = dict(public_response_payload)
        if upstream_response_payload is not None:
            record.upstream_response_payload = dict(upstream_response_payload)
        return record

    def reverse_settled_resource(
        self,
        *,
        resource_type: str,
        resource_id: UUID,
        reason: str,
        public_response_payload: dict | None = None,
        upstream_response_payload: dict | None = None,
    ) -> UsageRecord | None:
        record = self._crud.get_for_resource_update(resource_type=resource_type, resource_id=resource_id)
        if record is None or record.status == UsageRecordStatus.refunded:
            return record
        if record.status != UsageRecordStatus.succeeded:
            raise ValueError("使用记录不是已结算状态，不能冲正")
        self._wallet.refund_usage_balance(
            user_id=record.user_id, usage_record_id=record.id, amount=record.amount, reason=reason
        )
        now = datetime.now(UTC)
        record.status = UsageRecordStatus.refunded
        record.completed_at = now
        if record.started_at is not None:
            record.duration_ms = int((now - record.started_at).total_seconds() * 1000)
        if public_response_payload is not None:
            record.public_response_payload = dict(public_response_payload)
        if upstream_response_payload is not None:
            record.upstream_response_payload = dict(upstream_response_payload)
        return record

    def list_owned(self, **kwargs):
        return self._crud.list_owned(**kwargs)

    def get_owned(self, *, usage_record_id: UUID, user_id: UUID) -> UsageRecord:
        record = self._crud.get_owned(usage_record_id=usage_record_id, user_id=user_id)
        if record is None:
            raise NotFoundError("使用记录不存在")
        return record

    def list_admin(self, **kwargs):
        return self._crud.list_admin(**kwargs)

    def get(self, usage_record_id: UUID) -> UsageRecord | None:
        record = self._crud.get(usage_record_id)
        if record is None:
            raise NotFoundError("使用记录不存在")
        return record
