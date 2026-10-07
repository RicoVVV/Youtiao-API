import re
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.core.config import Settings
from app.core.errors import AuthenticationProviderUnavailableError, ValidationError
from app.core.secret_box import SMTP_CONFIG_PURPOSE, derive_fernet
from app.modules.system_settings.crud import SystemSettingsCrud
from app.modules.system_settings.model import SystemSetting

DEFAULT_SYSTEM_NAME = "Youtiao API"
DEFAULT_FOOTER_TEXT = """
<p>
  © 2026 您的公司。保留所有权利。
  <a href="https://beian.miit.gov.cn/" target="_blank" rel="noopener noreferrer" style="color: inherit;">备案号</a>
</p>
"""
DEFAULT_HOMEPAGE_CONTENT = "欢迎使用我们的 Youtiao API..."
KEEP_PASSWORD_SENTINEL = "__keep__"
"""SMTP 密码未提交时的哨兵值：保留原密码；空字符串表示清空，其他值表示加密替换。"""
SMTP_SECURITY_OPTIONS = frozenset({"none", "starttls", "ssl"})
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class SmtpConfigEncryptionError(AuthenticationProviderUnavailableError):
    """运行期 SMTP 密码无法解密时抛出，由全局异常处理器映射为 503 服务不可用。"""


class SystemSettingsApplicationService:
    public_fields = (
        "system_name",
        "server_url",
        "logo_url",
        "footer_text",
        "about_content",
        "homepage_content",
        "terms_of_service",
        "privacy_policy",
        "email_verification_enabled",
    )
    admin_fields = (
        "smtp_host",
        "smtp_port",
        "smtp_security",
        "smtp_username",
        "smtp_from_email",
        "smtp_from_name",
    )
    _text_fields = (
        "system_name",
        "server_url",
        "logo_url",
        "footer_text",
        "about_content",
        "homepage_content",
        "terms_of_service",
        "privacy_policy",
        "smtp_host",
        "smtp_username",
        "smtp_from_email",
        "smtp_from_name",
    )
    _nullable_skip_fields = ("email_verification_enabled", "smtp_port", "smtp_security")

    def __init__(self, session: Session, settings: Settings) -> None:
        self._session = session
        self._settings = settings
        self._crud = SystemSettingsCrud(session)

    def get_public_settings(self) -> dict[str, Any]:
        return self._public_projection(self._get_or_create_default())

    def get_admin_settings(self) -> dict[str, Any]:
        return self._admin_projection(self._get_or_create_default())

    def update_admin_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        """更新系统设置；SMTP 密码按哨兵保留、空串清空、非空加密替换，开启邮箱验证时校验发信配置完整。"""

        values: dict[str, Any] = {}
        for field in self._text_fields:
            if field in payload:
                values[field] = payload[field] or ""
        for field in self.admin_fields:
            if isinstance(values.get(field), str):
                values[field] = values[field].strip()
        for field in self._nullable_skip_fields:
            if payload.get(field) is not None:
                values[field] = payload[field]
        if "smtp_security" in values and values["smtp_security"] not in SMTP_SECURITY_OPTIONS:
            raise ValidationError("SMTP 加密方式必须是 none、starttls 或 ssl")
        password = payload.get("smtp_password", KEEP_PASSWORD_SENTINEL)
        if password is not None and password != KEEP_PASSWORD_SENTINEL:
            values["smtp_password_ciphertext"] = self._encrypt(password) if password else ""
        setting = self._get_or_create_default()
        if values:
            try:
                self._crud.update(setting, values)
                if setting.email_verification_enabled:
                    self._validate_smtp_ready(setting)
                self._session.commit()
            except Exception:
                self._session.rollback()
                raise
        return self._admin_projection(setting)

    def get_smtp_runtime_config(self) -> dict[str, Any]:
        """返回已解密的 SMTP 运行配置，仅供服务端发信使用，禁止写入响应或日志。"""

        setting = self._get_or_create_default()
        password = self._decrypt(setting.smtp_password_ciphertext) if setting.smtp_password_ciphertext else ""
        return {
            "enabled": setting.email_verification_enabled,
            "host": setting.smtp_host,
            "port": setting.smtp_port,
            "security": setting.smtp_security,
            "username": setting.smtp_username,
            "password": password,
            "from_email": setting.smtp_from_email,
            "from_name": setting.smtp_from_name or setting.system_name,
        }

    def _get_or_create_default(self) -> SystemSetting:
        setting = self._crud.get()
        if setting is not None:
            return setting
        try:
            setting = self._crud.create(self._default_values())
            self._session.commit()
            return setting
        except IntegrityError:
            self._session.rollback()
            setting = self._crud.get()
            if setting is None:
                raise
            return setting

    def _default_values(self) -> dict[str, str]:
        return {
            "system_name": DEFAULT_SYSTEM_NAME,
            "server_url": self._settings.public_base_url,
            "logo_url": "",
            "footer_text": DEFAULT_FOOTER_TEXT,
            "about_content": "",
            "homepage_content": DEFAULT_HOMEPAGE_CONTENT,
            "terms_of_service": "",
            "privacy_policy": "",
        }

    def _encrypt(self, plaintext: str) -> str:
        return self._fernet().encrypt(plaintext.encode()).decode()

    def _decrypt(self, ciphertext: str) -> str:
        try:
            return self._fernet().decrypt(ciphertext.encode()).decode()
        except InvalidToken as exc:
            raise SmtpConfigEncryptionError("SMTP 密码密文无法解密") from exc

    def _fernet(self) -> Fernet:
        return derive_fernet(self._settings.jwt_signing_key, SMTP_CONFIG_PURPOSE)

    @staticmethod
    def _validate_smtp_ready(setting: SystemSetting) -> None:
        """校验启用邮箱验证所需的 SMTP 配置；用户名缺失时发信代码会跳过登录，必须显式拒绝。"""

        if not setting.smtp_host:
            raise ValidationError("开启邮箱验证前必须配置 SMTP 服务器地址")
        if not 1 <= setting.smtp_port <= 65535:
            raise ValidationError("SMTP 端口必须在 1 到 65535 之间")
        if setting.smtp_security not in SMTP_SECURITY_OPTIONS:
            raise ValidationError("SMTP 加密方式必须是 none、starttls 或 ssl")
        if not setting.smtp_username:
            raise ValidationError("开启邮箱验证前必须配置 SMTP 用户名")
        if not setting.smtp_password_ciphertext:
            raise ValidationError("开启邮箱验证前必须配置 SMTP 密码")
        if not _EMAIL_PATTERN.match(setting.smtp_from_email):
            raise ValidationError("开启邮箱验证前必须配置有效的发件人邮箱")

    @classmethod
    def _public_projection(cls, setting: SystemSetting) -> dict[str, Any]:
        return {field: getattr(setting, field) for field in cls.public_fields}

    @classmethod
    def _admin_projection(cls, setting: SystemSetting) -> dict[str, Any]:
        projection = cls._public_projection(setting)
        projection.update({field: getattr(setting, field) for field in cls.admin_fields})
        projection["smtp_password_configured"] = bool(setting.smtp_password_ciphertext)
        return projection
