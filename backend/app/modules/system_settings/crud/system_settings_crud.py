from sqlmodel import Session

from app.modules.system_settings.model import SystemSetting
from app.modules.system_settings.model.system_setting import SYSTEM_SETTINGS_ID


class SystemSettingsCrud:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self) -> SystemSetting | None:
        return self._session.get(SystemSetting, SYSTEM_SETTINGS_ID)

    def create(self, values: dict[str, str]) -> SystemSetting:
        setting = SystemSetting(id=SYSTEM_SETTINGS_ID, **values)
        self._session.add(setting)
        return setting

    def update(self, setting: SystemSetting, values: dict[str, str]) -> SystemSetting:
        for key, value in values.items():
            setattr(setting, key, value)
        self._session.add(setting)
        return setting
