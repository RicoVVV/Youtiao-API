from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.core.config import Settings
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


class SystemSettingsApplicationService:
    fields = (
        "system_name",
        "server_url",
        "logo_url",
        "footer_text",
        "about_content",
        "homepage_content",
        "terms_of_service",
        "privacy_policy",
    )

    def __init__(self, session: Session, settings: Settings) -> None:
        self._session = session
        self._settings = settings
        self._crud = SystemSettingsCrud(session)

    def get_public_settings(self) -> dict[str, str]:
        return self._projection(self._get_or_create_default())

    def get_admin_settings(self) -> dict[str, str]:
        return self._projection(self._get_or_create_default())

    def update_admin_settings(self, payload: dict[str, str | None]) -> dict[str, str]:
        values = {field: value or "" for field, value in payload.items() if field in self.fields}
        setting = self._get_or_create_default()
        if values:
            try:
                self._crud.update(setting, values)
                self._session.commit()
            except Exception:
                self._session.rollback()
                raise
        return self._projection(setting)

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

    @classmethod
    def _projection(cls, setting: SystemSetting) -> dict[str, str]:
        return {field: getattr(setting, field) for field in cls.fields}
