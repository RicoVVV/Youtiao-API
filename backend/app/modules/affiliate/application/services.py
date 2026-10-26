"""邀请返利用例服务，承载绑定、返利计算、解冻与转入余额。"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlmodel import Session

from app.core.affiliate import (
    calculate_rebate,
    clamp_rebate_rate,
    is_valid_affiliate_code,
    mask_identity,
    normalize_affiliate_code,
)
from app.core.config import get_settings
from app.core.errors import NotFoundError, ValidationError
from app.modules.affiliate.crud.affiliate_crud import AffiliateCrud
from app.modules.affiliate.model import AffiliateLedger, AffiliateLedgerAction, UserAffiliate
from app.modules.system_settings.application.services import SystemSettingsApplicationService
from app.modules.wallet.application.services import WalletApplicationService
from app.modules.wallet.model import BalanceRecordType, RechargeOrder, RechargeOrderStatus


@dataclass(frozen=True, slots=True)
class AffiliateConfig:
    """邀请返利运行期配置快照。"""

    enabled: bool
    rebate_rate_percent: Decimal
    freeze_hours: int
    duration_days: int
    per_invitee_cap: Decimal
    signup_bonus: Decimal


class AffiliateApplicationService:
    """处理用户侧邀请返利用例，不自行提交非转出类事务。"""

    def __init__(self, session: Session) -> None:
        """绑定请求级会话并初始化返利仓储与设置服务。"""

        self._session = session
        self._crud = AffiliateCrud(session)
        self._settings = SystemSettingsApplicationService(session, get_settings())
        self._wallets = WalletApplicationService(session)

    def get_detail(self, user_id: UUID) -> dict:
        """返回邀请码、邀请链接、有效比例、额度与注册赠送额度，并顺带解冻到期返利。"""

        try:
            _, created = self._ensure_profile(user_id)
            thawed = self._crud.thaw_frozen(user_id)
            if created or thawed > 0:
                self._session.commit()
        except Exception:
            self._session.rollback()
            raise
        profile = self._crud.get_by_user_id(user_id)
        if profile is None:
            raise NotFoundError("邀请返利档案不存在")
        config = self._config()
        invitees = self._crud.list_invitees(user_id, page=1, page_size=20)
        return {
            "enabled": config.enabled,
            "aff_code": profile.aff_code,
            "invite_url": self._invite_url(profile.aff_code),
            "effective_rebate_rate_percent": _rate(profile.rebate_rate_percent, config.rebate_rate_percent),
            "aff_count": profile.aff_count,
            "available_quota": _amount(profile.available_quota),
            "frozen_quota": _amount(profile.frozen_quota),
            "history_quota": _amount(profile.history_quota),
            "signup_bonus": _amount(config.signup_bonus),
            "invitees": [
                {
                    "user_id": str(invitee.user_id),
                    "username": mask_identity(user.username),
                    "created_at": invitee.created_at,
                    "total_rebate": _amount(total_rebate),
                }
                for invitee, user, total_rebate in invitees
            ],
        }

    def list_invitees(self, user_id: UUID, *, page: int, page_size: int) -> dict:
        """分页返回当前用户邀请的被邀请人及返利贡献。"""

        total = self._crud.count_invitees(user_id)
        rows = self._crud.list_invitees(user_id, page=page, page_size=page_size)
        return {
            "items": [
                {
                    "user_id": str(invitee.user_id),
                    "username": mask_identity(user.username),
                    "created_at": invitee.created_at,
                    "total_rebate": _amount(total_rebate),
                }
                for invitee, user, total_rebate in rows
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def list_records(self, user_id: UUID, *, page: int, page_size: int) -> dict:
        """分页返回当前用户的返利产生与转出流水。"""

        total = self._crud.count_ledger(user_id)
        rows = self._crud.list_ledger(user_id, page=page, page_size=page_size)
        return {
            "items": [
                {
                    "id": str(ledger.id),
                    "action": ledger.action.value,
                    "amount": _amount(ledger.amount),
                    "source_username": mask_identity(source_username) if source_username else None,
                    "order_no": order_no,
                    "created_at": ledger.created_at,
                }
                for ledger, source_username, order_no in rows
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def validate_binding_code(self, raw_code: str | None) -> None:
        """注册前预校验邀请码，避免无效码在邮箱验证码被消费后才失败。"""

        config = self._config()
        if not config.enabled:
            return
        code = normalize_affiliate_code(raw_code)
        if not code:
            return
        if not is_valid_affiliate_code(code):
            raise ValidationError("邀请码格式不正确", code="affiliate.code_invalid", params={})
        self._resolve_inviter(code)

    def bind_inviter_by_code(self, *, user_id: UUID, raw_code: str | None) -> bool:
        """注册阶段按邀请码绑定上级；总开关关闭时静默忽略。

        返回值：是否实际建立邀请关系；未提交邀请码或返利总开关关闭时返回 False。
        """

        config = self._config()
        if not config.enabled:
            return False
        code = normalize_affiliate_code(raw_code)
        if not code:
            return False
        if not is_valid_affiliate_code(code):
            raise ValidationError("邀请码格式不正确", code="affiliate.code_invalid", params={})
        invitee = self._crud.get_by_user_id(user_id)
        if invitee is not None and invitee.inviter_id is not None:
            raise ValidationError("已绑定邀请人，不能重复绑定", code="affiliate.already_bound", params={})
        inviter = self._resolve_inviter(code)
        if inviter.user_id == user_id:
            raise ValidationError("邀请码无效", code="affiliate.code_invalid", params={})
        if invitee is None:
            self._crud.ensure_user_affiliate(user_id)
        if not self._crud.bind_inviter(user_id, inviter.user_id):
            raise ValidationError("已绑定邀请人，不能重复绑定", code="affiliate.already_bound", params={})
        return True

    def grant_signup_bonus(self, user_id: UUID) -> Decimal:
        """向通过邀请码或邀请链接注册的新用户一次性赠送余额。

        参数：user_id 为刚建立邀请关系的被邀请人。
        返回值：本次赠送金额；未配置赠送额度时返回 0。
        副作用：在余额明细中写入一条 ``signup_bonus`` 类型记录，不自行提交事务。
        """

        bonus = self._config().signup_bonus
        if bonus <= 0:
            return Decimal("0")
        self._wallets.grant(
            user_id=user_id,
            amount=bonus,
            record_type=BalanceRecordType.signup_bonus,
            reason="邀请注册赠送额度",
        )
        return bonus

    def on_user_deleted(self, user_id: UUID) -> None:
        """用户注销时回退其邀请人的绑定人数，保留历史关系供恢复使用。"""

        profile = self._crud.get_by_user_id(user_id)
        if profile is not None and profile.inviter_id is not None:
            self._crud.decrement_invite_count(profile.inviter_id)

    def on_user_restored(self, user_id: UUID) -> None:
        """用户恢复时补回其邀请人的绑定人数。"""

        profile = self._crud.get_by_user_id(user_id)
        if profile is not None and profile.inviter_id is not None:
            self._crud.increment_invite_count(profile.inviter_id)

    def accrue_for_order(self, order: RechargeOrder | None) -> Decimal:
        """按已支付订单为邀请人累计返利；同一订单重复调用不会重复入账。"""

        if order is None or order.status != RechargeOrderStatus.paid:
            return Decimal("0")
        config = self._config()
        if not config.enabled:
            return Decimal("0")
        invitee = self._crud.get_by_user_id(order.user_id)
        if invitee is None or invitee.inviter_id is None or invitee.inviter_id == order.user_id:
            return Decimal("0")
        if self._crud.is_user_deleted(invitee.user_id):
            return Decimal("0")
        now = datetime.now(UTC)
        if (
            config.duration_days > 0
            and invitee.created_at is not None
            and now > invitee.created_at + timedelta(days=config.duration_days)
        ):
            return Decimal("0")
        inviter = (
            self._crud.get_by_user_id_for_update(invitee.inviter_id)
            if config.per_invitee_cap > 0
            else self._crud.get_by_user_id(invitee.inviter_id)
        )
        if inviter is None:
            return Decimal("0")
        if self._crud.is_user_deleted(inviter.user_id):
            return Decimal("0")
        rate = (
            clamp_rebate_rate(inviter.rebate_rate_percent)
            if inviter.rebate_rate_percent is not None
            else config.rebate_rate_percent
        )
        rebate = calculate_rebate(order.amount, rate)
        if rebate <= 0:
            return Decimal("0")
        if config.per_invitee_cap > 0:
            existing = self._crud.get_accrued_total(inviter.user_id, invitee.user_id)
            remaining = config.per_invitee_cap - existing
            if remaining <= 0:
                return Decimal("0")
            if rebate > remaining:
                rebate = remaining
        frozen_until = now + timedelta(hours=config.freeze_hours) if config.freeze_hours > 0 else None
        ledger = AffiliateLedger(
            user_id=inviter.user_id,
            action=AffiliateLedgerAction.accrue,
            amount=rebate,
            source_user_id=invitee.user_id,
            source_order_id=order.id,
            frozen_until=frozen_until,
        )
        if not self._crud.create_accrual(ledger):
            return Decimal("0")
        self._crud.add_accrued_quota(inviter.user_id, rebate, frozen=frozen_until is not None)
        return rebate

    def transfer_quota(self, user_id: UUID) -> dict:
        """把全部可用返利额度转入钱包余额并记录快照。"""

        try:
            profile = self._crud.get_by_user_id_for_update(user_id)
            if profile is None:
                raise ValidationError("暂无可转入的邀请返利", code="affiliate.quota_empty", params={})
            self._crud.thaw_frozen(user_id)
            self._session.refresh(profile)
            amount = _decimal(profile.available_quota)
            if amount <= 0:
                raise ValidationError("暂无可转入的邀请返利", code="affiliate.quota_empty", params={})
            profile.available_quota = Decimal("0")
            self._session.flush()
            self._wallets.grant(
                user_id=user_id,
                amount=amount,
                record_type=BalanceRecordType.affiliate_rebate,
                reason="邀请返利转入余额",
            )
            wallet = self._wallets.get_wallet_by_user_id(user_id)
            if wallet is None:
                raise NotFoundError("用户钱包不存在")
            self._crud.add_transfer_ledger(
                AffiliateLedger(
                    user_id=user_id,
                    action=AffiliateLedgerAction.transfer,
                    amount=amount,
                    balance_after=wallet.balance,
                    available_quota_after=profile.available_quota,
                    frozen_quota_after=profile.frozen_quota,
                    history_quota_after=profile.history_quota,
                )
            )
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
        return {"transferred_quota": _amount(amount), "balance": _amount(wallet.balance)}

    def _ensure_profile(self, user_id: UUID) -> tuple[UserAffiliate, bool]:
        """读取用户档案，不存在时创建并返回是否新建。"""

        profile = self._crud.get_by_user_id(user_id)
        if profile is not None:
            return profile, False
        return self._crud.ensure_user_affiliate(user_id), True

    def _resolve_inviter(self, code: str) -> UserAffiliate:
        """按邀请码读取可用邀请人；码不存在或邀请人已注销时统一报无效。"""

        inviter = self._crud.get_by_code(code)
        if inviter is None or self._crud.is_user_deleted(inviter.user_id):
            raise ValidationError("邀请码无效", code="affiliate.code_invalid", params={})
        return inviter

    def _config(self) -> AffiliateConfig:
        """从系统设置读取邀请返利配置。"""

        raw = self._settings.get_affiliate_settings()
        return AffiliateConfig(
            enabled=bool(raw["enabled"]),
            rebate_rate_percent=clamp_rebate_rate(raw["rebate_rate_percent"]),
            freeze_hours=int(raw["freeze_hours"]),
            duration_days=int(raw["duration_days"]),
            per_invitee_cap=_decimal(raw["per_invitee_cap"]),
            signup_bonus=_decimal(raw["signup_bonus"]),
        )

    def _invite_url(self, aff_code: str) -> str:
        """按站点公开地址拼接邀请注册链接。"""

        public = self._settings.get_public_settings()
        base_url = str(public.get("server_url") or "").rstrip("/")
        return f"{base_url}/register?aff={aff_code}" if base_url else f"/register?aff={aff_code}"


def _decimal(value) -> Decimal:
    """把数据库或配置值转换为 Decimal。"""

    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _amount(value) -> str:
    """把金额格式化为固定 6 位小数字符串。"""

    return f"{_decimal(value):.6f}"


def _rate(user_rate, global_rate) -> str:
    """优先使用用户专属比例，否则回退全局比例。"""

    effective = clamp_rebate_rate(user_rate) if user_rate is not None else clamp_rebate_rate(global_rate)
    return f"{effective:.2f}"
