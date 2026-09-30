"""注册邮箱验证用例：发送验证码与校验。"""

import re

from sqlmodel import Session

from app.core.config import Settings
from app.core.errors import ConflictError, ValidationError
from app.infrastructure.email.smtp_client import send_email
from app.infrastructure.redis.rate_limiter import enforce_auth_rate_limit
from app.modules.system_settings.application.services import SystemSettingsApplicationService
from app.modules.user.crud.user_crud import UserCrud
from app.modules.user.runtime.email_code_store import (
    CODE_TTL_SECONDS,
    check_cooldown,
    consume_code,
    generate_code,
    release_code,
    save_code,
)

_VERIFICATION_CODE_SUBJECT = "您的注册验证码"
_EMAIL_CODE_RATE_LIMIT_SCOPE = "email-code"
_EMAIL_CODE_RATE_LIMIT = 10  # 同一 IP 每窗口最多 10 次
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class EmailVerificationNotEnabledError(ValidationError):
    """邮箱验证功能未开启时抛出。"""


class EmailAlreadyRegisteredError(ConflictError):
    """邮箱已被注册时抛出。"""


class EmailVerificationService:
    """注册邮箱验证码的发送与消费用例。"""

    def __init__(self, session: Session, settings: Settings) -> None:
        self._session = session
        self._settings = settings
        self._users = UserCrud(session)
        self._system_settings = SystemSettingsApplicationService(session, settings)

    def send_registration_code(self, *, email: str, client_host: str) -> None:
        """向指定邮箱发送注册验证码。

        异常：
        - EmailVerificationNotEnabledError：开关未开启
        - ValidationError：邮箱格式不合法
        - EmailAlreadyRegisteredError：邮箱已被注册
        - RateLimitExceededError：IP 限流或邮箱冷却
        - AuthenticationProviderUnavailableError：SMTP 或 Redis 不可用
        - AuthenticationRateLimitUnavailableError：限流服务不可用
        """

        email = self.normalize_email(email)
        smtp_config = self._system_settings.get_smtp_runtime_config()
        if not smtp_config["enabled"]:
            raise EmailVerificationNotEnabledError("邮箱验证功能未开启")
        enforce_auth_rate_limit(
            scope=_EMAIL_CODE_RATE_LIMIT_SCOPE,
            client_host=client_host,
            limit=_EMAIL_CODE_RATE_LIMIT,
        )
        check_cooldown(email)
        if self._users.get_by_email(email) is not None:
            raise EmailAlreadyRegisteredError("该邮箱已被注册")
        code = generate_code()
        save_code(email, code)
        try:
            send_email(
                host=smtp_config["host"],
                port=smtp_config["port"],
                security=smtp_config["security"],
                username=smtp_config["username"],
                password=smtp_config["password"],
                from_email=smtp_config["from_email"],
                from_name=smtp_config["from_name"],
                to_email=email,
                subject=_VERIFICATION_CODE_SUBJECT,
                body=f"您的注册验证码为：{code}，{CODE_TTL_SECONDS // 60} 分钟内有效。",
            )
        except Exception:
            # 发送失败时撤销刚写入的验证码与冷却标记，避免无效验证码积压并允许立即重试。
            release_code(email)
            raise

    @staticmethod
    def consume_registration_code(*, email: str, code: str) -> None:
        """校验并消费验证码，失败时抛出 ValidationError。"""

        consume_code(EmailVerificationService.normalize_email(email), code)

    @staticmethod
    def normalize_email(email: str) -> str:
        """去除首尾空白并转小写，格式不合法时抛出 ValidationError。"""

        normalized = email.strip().lower()
        if not _EMAIL_PATTERN.match(normalized):
            raise ValidationError("邮箱格式不合法")
        return normalized
