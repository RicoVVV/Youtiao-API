"""管理员邀请返利 HTTP 契约。"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class AdminAffiliateAccrueRecordItem(BaseModel):
    id: UUID
    inviter_id: UUID
    inviter_username: str
    invitee_id: UUID | None
    invitee_username: str | None
    order_no: str | None
    order_amount: str | None
    rebate_amount: str
    created_at: datetime | None


class AdminAffiliateAccrueListResponse(BaseModel):
    items: list[AdminAffiliateAccrueRecordItem]
    total: int
    page: int
    page_size: int


class AdminAffiliateTransferRecordItem(BaseModel):
    id: UUID
    user_id: UUID
    username: str
    amount: str
    balance_after: str | None
    available_quota_after: str | None
    frozen_quota_after: str | None
    history_quota_after: str | None
    created_at: datetime | None


class AdminAffiliateTransferListResponse(BaseModel):
    items: list[AdminAffiliateTransferRecordItem]
    total: int
    page: int
    page_size: int


class AdminAffiliateUserItem(BaseModel):
    user_id: UUID
    username: str
    aff_code: str
    inviter_id: UUID | None
    inviter_username: str | None
    aff_count: int
    available_quota: str
    frozen_quota: str
    history_quota: str
    created_at: datetime | None


class AdminAffiliateUserListResponse(BaseModel):
    items: list[AdminAffiliateUserItem]
    total: int
    page: int
    page_size: int


class AdminAffiliateUserOverview(BaseModel):
    user_id: UUID
    username: str
    aff_code: str
    inviter_id: UUID | None
    inviter_username: str | None
    rebate_rate_percent: str
    rebate_rate_custom: bool
    invited_count: int
    rebated_invitee_count: int
    available_quota: str
    frozen_quota: str
    history_quota: str
    created_at: datetime | None
