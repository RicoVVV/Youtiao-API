"""用户资料应用服务，编排账号查询并返回安全的内部数据投影。"""

from decimal import Decimal
from uuid import UUID

from sqlmodel import Session

from app.core.config import get_settings
from app.core.errors import NotFoundError, ValidationError
from app.modules.membership.application.services import MembershipQueryService
from app.modules.user.application.auth.contracts import UserProfileData
from app.modules.user.application.auth.email_verification import EmailVerificationService
from app.modules.user.crud.user_crud import UserCrud
from app.modules.wallet.application.balance_alert import BalanceAlertApplicationService


class UserProfileApplicationService:
    """处理当前用户资料查询，不向 HTTP 层泄露 ORM 实体。"""

    def __init__(self, session: Session) -> None:
        """绑定由调用方管理的数据库会话，不提交或回滚事务。

        参数：session 为当前请求的数据库会话。
        返回值：无。
        异常/副作用：不执行事务边界控制。
        """

        self._session = session
        self._users = UserCrud(session)
        self._memberships = MembershipQueryService(session)

    def get_profile(self, user_id: UUID) -> UserProfileData:
        """查询用户资料并转换为不含密码与认证状态的安全投影，含当前会员状态。

        参数：user_id 为已通过鉴权的用户标识。
        返回值：用户不存在时返回 None，否则返回资料数据。
        异常/副作用：仅执行只读数据库查询。
        """

        statistics = self._users.get_profile_statistics(user_id)
        if statistics is None:
            raise NotFoundError("用户不存在")
        user, balance, usage = statistics
        return UserProfileData(
            id=user.id,
            username=user.username,
            is_active=user.is_active,
            is_admin=user.is_admin,
            created_at=user.created_at,
            balance=_format_amount(balance),
            usage=_format_amount(usage),
            balance_alert_threshold=_format_threshold(user.balance_alert_threshold),
            email=user.email,
            balance_alert_email=user.balance_alert_email,
            membership=self._memberships.get_active_membership(user_id),
        )

    def update_balance_alert_settings(
        self, *, user_id: UUID, threshold: Decimal | None, email: str | None
    ) -> dict[str, str | None]:
        """更新用户自设的余额预警阈值与收件邮箱。

        参数：threshold 为正数阈值或 None（关闭预警）；email 为自设收件邮箱，留空时回退到注册邮箱。
        异常：阈值非正数、邮箱格式不合法，或在未绑定注册邮箱的情况下开启预警却未填写邮箱时返回 422。
        副作用：提交阈值与邮箱变更，并重置该用户的低余额提醒周期，失败时回滚。
        """

        user = self._users.get_by_id(user_id)
        if user is None:
            raise NotFoundError("用户不存在")
        if threshold is not None and threshold <= 0:
            raise ValidationError("余额预警阈值必须大于 0")
        raw_email = (email or "").strip()
        notification_email = EmailVerificationService.normalize_email(raw_email) if raw_email else None
        if threshold is not None and not (notification_email or user.email):
            raise ValidationError("当前账号未绑定邮箱，请填写接收余额预警的邮箱")
        try:
            self._users.set_balance_alert_settings(user, threshold=threshold, email=notification_email)
            # 修改预警设置视为开启新的低余额周期，避免旧阈值下的提醒记录压掉新阈值应发的邮件。
            BalanceAlertApplicationService(self._session, get_settings()).reset_episode(user_id)
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
        return {
            "balance_alert_threshold": _format_threshold(user.balance_alert_threshold),
            "balance_alert_email": user.balance_alert_email,
        }


def _format_amount(amount: Decimal) -> str:
    """将钱包十进制金额格式化为两位小数的账户展示值。"""

    return f"{amount:.2f}"


def _format_threshold(threshold: Decimal | None) -> str | None:
    """格式化用户余额预警阈值，未设置时返回空值。"""

    return None if threshold is None else f"{threshold:.6f}"
