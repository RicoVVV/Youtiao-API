import re
from decimal import Decimal, InvalidOperation
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.core.affiliate import (
    DEFAULT_AFFILIATE_ENABLED,
    DEFAULT_REBATE_DURATION_DAYS,
    DEFAULT_REBATE_FREEZE_HOURS,
    DEFAULT_REBATE_PER_INVITEE_CAP,
    DEFAULT_REBATE_RATE_PERCENT,
    DEFAULT_SIGNUP_BONUS,
    MAX_REBATE_DURATION_DAYS,
    MAX_REBATE_FREEZE_HOURS,
    MAX_SIGNUP_BONUS,
    clamp_rebate_rate,
)
from app.core.channel_automation import (
    DEFAULT_CHANNEL_AUTOMATION_CONFIG,
    ChannelAutomationConfig,
    parse_keyword_text,
    parse_status_code_spec,
    set_channel_automation_config,
)
from app.core.config import Settings
from app.core.errors import AuthenticationProviderUnavailableError, ValidationError
from app.core.secret_box import SMTP_CONFIG_PURPOSE, derive_fernet
from app.modules.system_settings.crud import SystemSettingsCrud
from app.modules.system_settings.domain.sidebar_modules import (
    GROUP_KEYS,
    MODULE_KEYS,
    SIDEBAR_GROUPS,
    is_module_visible,
    normalize_visibility,
    visible_modules,
)
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
        "affiliate_enabled",
        "affiliate_signup_bonus",
    )
    admin_fields = (
        "smtp_host",
        "smtp_port",
        "smtp_security",
        "smtp_username",
        "smtp_from_email",
        "smtp_from_name",
        "balance_alert_enabled",
        "channel_probe_enabled",
        "channel_probe_interval_minutes",
        "channel_probe_timeout_seconds",
        "channel_auto_disable_enabled",
        "channel_auto_enable_enabled",
        "channel_auto_disable_status_codes",
        "channel_auto_retry_status_codes",
        "channel_auto_disable_keywords",
        "affiliate_rebate_rate_percent",
        "affiliate_rebate_freeze_hours",
        "affiliate_rebate_duration_days",
        "affiliate_rebate_per_invitee_cap",
        "affiliate_signup_bonus",
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
        "channel_auto_disable_status_codes",
        "channel_auto_retry_status_codes",
        "channel_auto_disable_keywords",
    )
    _nullable_skip_fields = (
        "email_verification_enabled",
        "smtp_port",
        "smtp_security",
        "balance_alert_enabled",
        "channel_probe_enabled",
        "channel_probe_interval_minutes",
        "channel_probe_timeout_seconds",
        "channel_auto_disable_enabled",
        "channel_auto_enable_enabled",
        "affiliate_enabled",
        "affiliate_rebate_rate_percent",
        "affiliate_rebate_freeze_hours",
        "affiliate_rebate_duration_days",
        "affiliate_rebate_per_invitee_cap",
        "affiliate_signup_bonus",
    )

    def __init__(self, session: Session, settings: Settings) -> None:
        self._session = session
        self._settings = settings
        self._crud = SystemSettingsCrud(session)

    def get_public_settings(self) -> dict[str, Any]:
        return self._public_projection(self._get_or_create_default())

    def get_affiliate_settings(self) -> dict[str, Any]:
        """只读返回邀请返利运行配置；配置行缺失时使用默认值且不写库。"""

        setting = self._crud.get()
        if setting is None:
            return {
                "enabled": DEFAULT_AFFILIATE_ENABLED,
                "rebate_rate_percent": DEFAULT_REBATE_RATE_PERCENT,
                "freeze_hours": DEFAULT_REBATE_FREEZE_HOURS,
                "duration_days": DEFAULT_REBATE_DURATION_DAYS,
                "per_invitee_cap": DEFAULT_REBATE_PER_INVITEE_CAP,
                "signup_bonus": DEFAULT_SIGNUP_BONUS,
            }
        return {
            "enabled": bool(setting.affiliate_enabled),
            "rebate_rate_percent": clamp_rebate_rate(setting.affiliate_rebate_rate_percent),
            "freeze_hours": _bounded_int(
                setting.affiliate_rebate_freeze_hours, DEFAULT_REBATE_FREEZE_HOURS, MAX_REBATE_FREEZE_HOURS
            ),
            "duration_days": _bounded_int(
                setting.affiliate_rebate_duration_days, DEFAULT_REBATE_DURATION_DAYS, MAX_REBATE_DURATION_DAYS
            ),
            "per_invitee_cap": _non_negative_decimal(setting.affiliate_rebate_per_invitee_cap),
            "signup_bonus": _non_negative_decimal(
                setting.affiliate_signup_bonus, DEFAULT_SIGNUP_BONUS, MAX_SIGNUP_BONUS
            ),
        }

    def get_admin_settings(self) -> dict[str, Any]:
        setting = self._get_or_create_default()
        set_channel_automation_config(self._channel_automation_config(setting))
        return self._admin_projection(setting)

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
                self._validate_balance_alert_ready(setting)
                if setting.email_verification_enabled:
                    self._validate_smtp_ready(setting)
                self._session.commit()
            except Exception:
                self._session.rollback()
                raise
            set_channel_automation_config(self._channel_automation_config(setting))
        return self._admin_projection(setting)

    def get_sidebar_modules(self) -> dict[str, Any]:
        """返回公开的侧边栏生效可见模块 key，供前端隐藏菜单。"""

        setting = self._get_or_create_default()
        return {"modules": visible_modules(setting.sidebar_visibility)}

    def get_admin_sidebar_modules(self) -> dict[str, Any]:
        """返回侧边栏目录与已补全默认值的完整开关表。"""

        return self._sidebar_projection(self._get_or_create_default())

    def update_admin_sidebar_modules(self, payload: dict[str, Any]) -> dict[str, Any]:
        """整体替换侧边栏可见性；未登记的分组或模块 key 一律拒绝，提交内容即落库内容。"""

        groups = dict(payload["groups"])
        modules = dict(payload["modules"])
        for key in sorted(set(groups) - set(GROUP_KEYS)):
            raise ValidationError(
                f"侧边栏分组 {key} 不存在",
                code="sidebar.unknown_group",
                params={"key": key},
            )
        for key in sorted(set(modules) - set(MODULE_KEYS)):
            raise ValidationError(
                f"侧边栏模块 {key} 不存在",
                code="sidebar.unknown_module",
                params={"key": key},
            )
        setting = self._get_or_create_default()
        try:
            self._crud.update(setting, {"sidebar_visibility": {"groups": groups, "modules": modules}})
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
        return self._sidebar_projection(setting)

    def is_sidebar_module_visible(self, module_key: str) -> bool:
        """判断模块当前是否可见；配置行缺失时视为全部可见，且不写库。"""

        setting = self._crud.get()
        visibility = setting.sidebar_visibility if setting is not None else {}
        return is_module_visible(visibility, module_key)

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

    def read_balance_alert_config(self) -> dict[str, Any]:
        """只读返回余额预警运行配置；配置行缺失或邮箱注册未开启时视为未开启，不写库。"""

        setting = self._crud.get()
        if setting is None or not setting.balance_alert_enabled or not setting.email_verification_enabled:
            return {"enabled": False, "system_name": "", "server_url": ""}
        return {
            "enabled": True,
            "system_name": setting.system_name or DEFAULT_SYSTEM_NAME,
            "server_url": setting.server_url,
        }

    def read_channel_automation_config(self) -> ChannelAutomationConfig:
        """只读返回渠道自动化配置；配置行缺失时使用默认值，不写库。"""

        return self._channel_automation_config(self._crud.get())

    def refresh_channel_automation_config(self) -> ChannelAutomationConfig:
        """重新读取并刷新进程内缓存，供后台任务与请求失败链路使用。"""

        config = self.read_channel_automation_config()
        set_channel_automation_config(config)
        return config

    @staticmethod
    def _channel_automation_config(setting: SystemSetting | None) -> ChannelAutomationConfig:
        """把持久化配置转换为运行期值对象；单个字段格式异常时回退默认值，避免影响请求链路。"""

        if setting is None:
            return DEFAULT_CHANNEL_AUTOMATION_CONFIG
        try:
            disable_codes = parse_status_code_spec(setting.channel_auto_disable_status_codes or "")
        except ValueError:
            disable_codes = DEFAULT_CHANNEL_AUTOMATION_CONFIG.auto_disable_status_codes
        try:
            retry_codes = parse_status_code_spec(setting.channel_auto_retry_status_codes or "")
        except ValueError:
            retry_codes = DEFAULT_CHANNEL_AUTOMATION_CONFIG.auto_retry_status_codes
        return ChannelAutomationConfig(
            probe_enabled=setting.channel_probe_enabled,
            probe_interval_seconds=max(1, setting.channel_probe_interval_minutes or 1) * 60,
            probe_timeout_seconds=max(1, setting.channel_probe_timeout_seconds or 1),
            auto_disable_enabled=setting.channel_auto_disable_enabled,
            auto_enable_enabled=setting.channel_auto_enable_enabled,
            auto_disable_status_codes=disable_codes,
            auto_retry_status_codes=retry_codes,
            auto_disable_keywords=parse_keyword_text(setting.channel_auto_disable_keywords or ""),
        )

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
    def _validate_balance_alert_ready(setting: SystemSetting) -> None:
        """余额预警依赖邮箱注册验证提供的用户邮箱。"""

        if not setting.balance_alert_enabled:
            return
        if not setting.email_verification_enabled:
            raise ValidationError("余额预警依赖邮箱注册验证，开启余额预警时必须同时开启邮箱注册验证")

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

    @staticmethod
    def _sidebar_projection(setting: SystemSetting) -> dict[str, Any]:
        """返回侧边栏目录与已补全默认值的完整分组、模块开关表。"""

        return {
            "catalog": {
                "groups": [{"key": group, "modules": list(modules)} for group, modules in SIDEBAR_GROUPS.items()]
            },
            "visibility": normalize_visibility(setting.sidebar_visibility),
        }


def _bounded_int(value: Any, default: int, maximum: int) -> int:
    """把配置整数限制在 0 到最大值之间。"""

    if value is None:
        return default
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return min(max(number, 0), maximum)


def _non_negative_decimal(
    value: Any, default: Decimal = DEFAULT_REBATE_PER_INVITEE_CAP, maximum: Decimal | None = None
) -> Decimal:
    """把配置金额限制为非负 Decimal，并按需限制上限。"""

    if value is None:
        return default
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return default
    amount = max(amount, Decimal("0"))
    return amount if maximum is None else min(amount, maximum)
