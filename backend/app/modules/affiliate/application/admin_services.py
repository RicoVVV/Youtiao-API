"""管理员邀请返利查询服务，提供只读的流水与用户概览。"""

from decimal import Decimal
from uuid import UUID

from sqlmodel import Session

from app.core.affiliate import clamp_rebate_rate
from app.core.config import get_settings
from app.core.errors import NotFoundError
from app.modules.affiliate.crud.affiliate_crud import AffiliateCrud
from app.modules.system_settings.application.services import SystemSettingsApplicationService


class AffiliateAdminService:
    """封装管理员侧邀请返利只读查询用例。"""

    def __init__(self, session: Session) -> None:
        """绑定请求级会话。"""

        self._session = session
        self._crud = AffiliateCrud(session)
        self._settings = SystemSettingsApplicationService(session, get_settings())

    def list_accrue_records(self, *, page: int, page_size: int) -> dict:
        """分页返回全部返利产生流水及来源订单。"""

        total = self._crud.count_accrue_records()
        rows = self._crud.list_accrue_records(page=page, page_size=page_size)
        return {
            "items": [
                {
                    "id": str(ledger.id),
                    "inviter_id": str(ledger.user_id),
                    "inviter_username": inviter_username,
                    "invitee_id": str(ledger.source_user_id) if ledger.source_user_id else None,
                    "invitee_username": invitee_username,
                    "order_no": order_no,
                    "order_amount": _amount(order_amount) if order_amount is not None else None,
                    "rebate_amount": _amount(ledger.amount),
                    "created_at": ledger.created_at,
                }
                for ledger, inviter_username, invitee_username, order_no, order_amount in rows
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def list_transfer_records(self, *, page: int, page_size: int) -> dict:
        """分页返回全部返利转入余额流水。"""

        total = self._crud.count_transfer_records()
        rows = self._crud.list_transfer_records(page=page, page_size=page_size)
        return {
            "items": [
                {
                    "id": str(ledger.id),
                    "user_id": str(ledger.user_id),
                    "username": username,
                    "amount": _amount(ledger.amount),
                    "balance_after": _optional_amount(ledger.balance_after),
                    "available_quota_after": _optional_amount(ledger.available_quota_after),
                    "frozen_quota_after": _optional_amount(ledger.frozen_quota_after),
                    "history_quota_after": _optional_amount(ledger.history_quota_after),
                    "created_at": ledger.created_at,
                }
                for ledger, username in rows
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def list_users(self, *, page: int, page_size: int, search: str | None = None) -> dict:
        """分页返回拥有邀请档案的用户。"""

        total = self._crud.count_users(search)
        rows = self._crud.list_users(page=page, page_size=page_size, search=search)
        return {
            "items": [
                {
                    "user_id": str(profile.user_id),
                    "username": user.username,
                    "aff_code": profile.aff_code,
                    "inviter_id": str(profile.inviter_id) if profile.inviter_id else None,
                    "inviter_username": inviter_username,
                    "aff_count": profile.aff_count,
                    "available_quota": _amount(profile.available_quota),
                    "frozen_quota": _amount(profile.frozen_quota),
                    "history_quota": _amount(profile.history_quota),
                    "created_at": profile.created_at,
                }
                for profile, user, inviter_username in rows
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def get_user_overview(self, user_id: UUID) -> dict:
        """返回单个用户的邀请码、有效比例与额度概览。"""

        row = self._crud.get_user_overview(user_id)
        if row is None:
            raise NotFoundError("邀请返利档案不存在")
        profile, user, inviter_username, rebated_invitee_count = row
        global_rate = self._settings.get_affiliate_settings()["rebate_rate_percent"]
        effective_rate = (
            clamp_rebate_rate(profile.rebate_rate_percent)
            if profile.rebate_rate_percent is not None
            else clamp_rebate_rate(global_rate)
        )
        return {
            "user_id": str(profile.user_id),
            "username": user.username,
            "aff_code": profile.aff_code,
            "inviter_id": str(profile.inviter_id) if profile.inviter_id else None,
            "inviter_username": inviter_username,
            "rebate_rate_percent": f"{effective_rate:.2f}",
            "rebate_rate_custom": profile.rebate_rate_percent is not None,
            "invited_count": profile.aff_count,
            "rebated_invitee_count": rebated_invitee_count,
            "available_quota": _amount(profile.available_quota),
            "frozen_quota": _amount(profile.frozen_quota),
            "history_quota": _amount(profile.history_quota),
            "created_at": profile.created_at,
        }


def _decimal(value) -> Decimal:
    """把数据库返回值转换为 Decimal。"""

    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _amount(value) -> str:
    """把金额格式化为固定 6 位小数字符串。"""

    return f"{_decimal(value):.6f}"


def _optional_amount(value) -> str | None:
    """可选金额保持原样返回空值。"""

    return None if value is None else _amount(value)
