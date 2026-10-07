"""计费应用服务。"""

import secrets
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlmodel import Session

from app.core.errors import NotFoundError, ValidationError
from app.modules.billing.crud import BillingCrud
from app.modules.billing.model import BillingAdjustment, RedemptionCode
from app.modules.wallet.application.services import WalletApplicationService
from app.modules.wallet.model import BalanceRecordType


class BillingApplicationService:
    """处理管理员账务调整和兑换码用例。"""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._crud = BillingCrud(session)
        self._wallets = WalletApplicationService(session)

    def adjust_balance(self, *, user_id: UUID, admin_id: UUID, amount: Decimal, reason: str | None = None) -> dict:
        if amount <= 0:
            raise ValidationError("授予金额必须为正数")
        try:
            record = self._wallets.grant(
                user_id=user_id,
                amount=amount,
                record_type=BalanceRecordType.admin_grant,
                reason=reason or "管理员余额调整",
                operator_id=admin_id,
            )
            self._crud.flush()
            adjustment = self._crud.add_adjustment(
                BillingAdjustment(
                    user_id=user_id,
                    admin_id=admin_id,
                    amount=amount,
                    reason=reason or "管理员余额调整",
                    balance_record_id=record.id,
                )
            )
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
        return self._adjustment_view(adjustment)

    def create_redemption_codes(
        self,
        *,
        admin_id: UUID,
        name: str,
        amount: Decimal,
        remark: str | None,
        expires_at: datetime | None,
        quantity: int = 1,
    ) -> dict:
        if amount <= 0:
            raise ValidationError("兑换金额必须为正")
        try:
            items = self._crud.add_redemption_codes(
                [
                    RedemptionCode(
                        name=name,
                        remark=remark,
                        expires_at=expires_at,
                        created_by_admin_id=admin_id,
                        code=f"rc-{secrets.token_urlsafe(24)}",
                        amount=amount,
                    )
                    for _ in range(quantity)
                ]
            )
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
        return {"items": [self._redemption_code_view(item) for item in items], "total": len(items)}

    def list_redemption_codes(self, *, page: int, page_size: int, name: str | None, status: str | None) -> dict:
        items, total = self._crud.list_redemption_codes(
            page=page, page_size=page_size, name=name, status=status, now=datetime.now(UTC)
        )
        return {
            "items": [self._redemption_code_view(item) for item in items],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def list_redemption_code_values(self, *, name: str | None, status: str | None) -> list[str]:
        """按管理端筛选条件返回全部兑换码明文，供导出 txt 使用。"""

        items = self._crud.list_redemption_codes_for_export(name=name, status=status, now=datetime.now(UTC))
        return [item.code for item in items]

    def get_redemption_code(self, code_id: UUID) -> dict:
        item = self._crud.get_redemption_code_by_id(code_id)
        if item is None:
            raise NotFoundError("兑换码不存在")
        return self._redemption_code_view(item)

    def update_redemption_code(
        self, *, code_id: UUID, name: str, remark: str | None, expires_at: datetime | None
    ) -> dict:
        item = self._get_editable_redemption_code(code_id, "更新")
        try:
            item.name, item.remark, item.expires_at = name, remark, expires_at
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
        return self._redemption_code_view(item)

    def change_redemption_code_status(self, *, code_id: UUID, active: bool) -> dict:
        item = self._get_editable_redemption_code(code_id, "切换状态")
        try:
            item.active = active
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
        return self._redemption_code_view(item)

    def redeem(self, *, user_id: UUID, raw_code: str) -> dict:
        try:
            item = self._crud.get_redemption_code_for_update(raw_code.strip())
            if (
                item is None
                or not item.active
                or (item.expires_at is not None and item.expires_at <= datetime.now(UTC))
            ):
                raise ValidationError("兑换码无效或已使用")
            if item.redeemed_by_user_id is not None:
                if item.redeemed_by_user_id == user_id:
                    wallet = self._wallets.get_wallet_by_user_id(user_id)
                    return {
                        "redemption_code_id": str(item.id),
                        "amount": str(item.amount),
                        "balance": str(wallet.balance),
                    }
                raise ValidationError("兑换码无效或已使用")
            self._wallets.grant(
                user_id=user_id,
                amount=item.amount,
                record_type=BalanceRecordType.redemption,
                reason="兑换码核销入账",
                redemption_code_id=item.id,
            )
            item.redeemed_by_user_id, item.redeemed_at = user_id, datetime.now(UTC)
            self._session.commit()
            wallet = self._wallets.get_wallet_by_user_id(user_id)
        except Exception:
            self._session.rollback()
            raise
        return {"redemption_code_id": str(item.id), "amount": str(item.amount), "balance": str(wallet.balance)}

    def _get_editable_redemption_code(self, code_id: UUID, action: str) -> RedemptionCode:
        item = self._crud.get_redemption_code_by_id(code_id)
        if item is None:
            raise NotFoundError("兑换码不存在")
        if item.redeemed_by_user_id is not None:
            raise ValidationError(
                f"已兑换兑换码不可{action}", code="billing.redemption_code_locked", params={"action": action}
            )
        return item

    @staticmethod
    def redemption_code_status(code: RedemptionCode, now: datetime | None = None) -> str:
        if code.redeemed_by_user_id is not None:
            return "redeemed"
        if not code.active:
            return "disabled"
        if code.expires_at is not None and code.expires_at <= (now or datetime.now(UTC)):
            return "expired"
        return "unused"

    def _redemption_code_view(self, item: RedemptionCode) -> dict:
        return {
            "id": str(item.id),
            "name": item.name,
            "remark": item.remark,
            "code": item.code,
            "amount": str(item.amount),
            "active": item.active,
            "status": self.redemption_code_status(item),
            "expires_at": item.expires_at,
            "created_at": item.created_at,
            "created_by_admin_id": str(item.created_by_admin_id) if item.created_by_admin_id else None,
            "redeemed_by_user_id": str(item.redeemed_by_user_id) if item.redeemed_by_user_id else None,
            "redeemed_at": item.redeemed_at,
        }

    @staticmethod
    def _adjustment_view(item: BillingAdjustment) -> dict:
        return {"id": str(item.id), "amount": str(item.amount), "reason": item.reason}
