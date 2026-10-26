"""邀请返利用户端 HTTP 契约。"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class AffiliateInviteeItem(BaseModel):
    user_id: UUID
    username: str
    created_at: datetime | None
    total_rebate: str


class AffiliateDetailResponse(BaseModel):
    enabled: bool
    aff_code: str
    invite_url: str
    effective_rebate_rate_percent: str
    aff_count: int
    available_quota: str
    frozen_quota: str
    history_quota: str
    signup_bonus: str
    invitees: list[AffiliateInviteeItem]


class AffiliateInviteeListResponse(BaseModel):
    items: list[AffiliateInviteeItem]
    total: int
    page: int
    page_size: int


class AffiliateLedgerItem(BaseModel):
    id: UUID
    action: str
    amount: str
    source_username: str | None
    order_no: str | None
    created_at: datetime | None


class AffiliateLedgerListResponse(BaseModel):
    items: list[AffiliateLedgerItem]
    total: int
    page: int
    page_size: int


class AffiliateTransferResponse(BaseModel):
    transferred_quota: str
    balance: str
