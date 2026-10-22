"""余额预警用例：在用户使用扣费后懒校验余额并向预留邮箱发送提醒。"""

import logging
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlmodel import Session

from app.core.config import Settings
from app.infrastructure.email.smtp_client import send_email
from app.modules.system_settings.application.services import SystemSettingsApplicationService
from app.modules.user.crud.user_crud import UserCrud
from app.modules.wallet.crud.balance_alert_crud import BalanceAlertCrud

logger = logging.getLogger(__name__)


class BalanceAlertApplicationService:
    """按使用后的余额变化判断是否需要发送额度即将用完的提醒邮件。

    只在扣费导致余额跌破阈值时发信，同一低余额周期只提醒一次；余额回升后再次跌破会重新提醒。
    """

    def __init__(self, session: Session, settings: Settings) -> None:
        self._session = session
        self._settings = settings
        self._system_settings = SystemSettingsApplicationService(session, settings)
        self._crud = BalanceAlertCrud(session)
        self._users = UserCrud(session)

    def evaluate_after_usage(self, *, user_id: UUID, balance_before: Decimal, balance_after: Decimal) -> bool:
        """在扣费后按用户自设阈值判断并发送提醒，返回是否实际发送。

        - 管理员未开启预警、邮箱注册验证未开启、用户无可用收件邮箱或未设置阈值时直接跳过；
        - 收件邮箱优先取用户自设的余额预警邮箱，未设置时回退到注册邮箱；
        - 本次扣费使余额从用户阈值上方跌到阈值及以下视为新一轮低余额，即使此前提醒过也会再次发送；
        - 余额原本就在阈值以下时，仅在该周期尚未提醒过时发送。
        """

        config = self._system_settings.read_balance_alert_config()
        if not config["enabled"]:
            return False
        user = self._users.get_by_id(user_id)
        if user is None or not user.is_active:
            return False
        to_email = user.balance_alert_email or user.email
        if not to_email:
            return False
        threshold = user.balance_alert_threshold
        if threshold is None or threshold <= 0 or balance_after > threshold:
            return False
        state = self._crud.get_alert_state(user_id)
        crossed_threshold = balance_before > threshold
        if not crossed_threshold and state is not None and state.alerted_at is not None:
            return False
        smtp_config = self._system_settings.get_smtp_runtime_config()
        try:
            send_email(
                host=smtp_config["host"],
                port=smtp_config["port"],
                security=smtp_config["security"],
                username=smtp_config["username"],
                password=smtp_config["password"],
                from_email=smtp_config["from_email"],
                from_name=smtp_config["from_name"],
                to_email=to_email,
                subject=f"{config['system_name']} low balance alert",
                body=_build_body(
                    username=user.username,
                    balance=balance_after,
                    threshold=threshold,
                    system_name=config["system_name"],
                    server_url=config["server_url"],
                ),
            )
        except Exception:
            # 清除旧的提醒标记，使本次发送失败后能在下一次使用时重试。
            self._crud.clear_alerted(user_id)
            raise
        self._crud.mark_alerted(user_id=user_id, balance=balance_after, alerted_at=datetime.now(UTC))
        return True

    def reset_episode(self, user_id: UUID) -> None:
        """清除用户当前低余额周期的提醒标记，使用户修改阈值后能按新阈值重新提醒。"""

        self._crud.clear_alerted(user_id)


def _build_body(
    *,
    username: str,
    balance: Decimal,
    threshold: Decimal,
    system_name: str,
    server_url: str,
) -> str:
    """构造纯文本提醒邮件正文；站点未配置地址时省略充值链接。"""

    lines = [
        f"Hello {username},",
        "",
        f"Your {system_name} account balance is running low.",
        "",
        f"Current balance: ${_format_amount(balance)}",
        f"Alert threshold: ${_format_amount(threshold)}",
        "",
        "Please top up your account to avoid service interruption.",
    ]
    if server_url:
        lines.extend(["", f"Recharge: {server_url.rstrip('/')}/console/billing"])
    lines.extend(["", "If you have already topped up, please ignore this email."])
    return "\n".join(lines)


def _format_amount(amount: Decimal) -> str:
    return f"{amount:.2f}"
