"""按请求类型维护监控数据模式与嗅探周期。

文本类型可以在 ``real`` 与 ``probe`` 之间切换；图片与视频只有 ``real``。
管理员切换后，管理侧与用户侧同一类型同步切换数据源。
"""

from sqlmodel import Session

from app.core.errors import ValidationError
from app.modules.monitoring.crud.traffic_setting_crud import MonitorTrafficSettingCrud
from app.modules.monitoring.model import (
    DEFAULT_MONITOR_MODES,
    DEFAULT_PROBE_INTERVAL_SECONDS,
    MAX_PROBE_INTERVAL_SECONDS,
    MIN_PROBE_INTERVAL_SECONDS,
    MODE_FIELD_BY_TYPE,
    MONITOR_MODE_PROBE,
    MONITOR_MODE_REAL,
    MONITOR_MODE_TYPES,
    MONITOR_MODES,
    MonitorTrafficSetting,
)


def _default_mode_values() -> dict[str, str]:
    """返回按列名展开的默认模式值。"""

    return {MODE_FIELD_BY_TYPE[request_type]: mode for request_type, mode in DEFAULT_MONITOR_MODES.items()}


class MonitorTrafficSettingsApplicationService:
    """维护按请求类型区分的监控数据模式与嗅探周期。"""

    def __init__(self, session: Session) -> None:
        """绑定调用方提供的事务会话。"""

        self._session = session
        self._settings = MonitorTrafficSettingCrud(session)

    def current_modes(self) -> dict[str, str]:
        """返回各请求类型当前生效的数据模式。"""

        record = self._settings.get()
        if record is None:
            return dict(DEFAULT_MONITOR_MODES)
        modes: dict[str, str] = {}
        for request_type in MONITOR_MODE_TYPES:
            value = getattr(record, MODE_FIELD_BY_TYPE[request_type], None)
            modes[request_type] = value if value in MONITOR_MODES else DEFAULT_MONITOR_MODES[request_type]
        # 图片与视频不支持嗅探，历史异常配置按真实请求处理。
        for request_type in ("image", "video"):
            if modes[request_type] == MONITOR_MODE_PROBE:
                modes[request_type] = MONITOR_MODE_REAL
        return modes

    def current_text_mode(self) -> str:
        """返回文本类型当前模式，供嗅探任务判断是否执行。"""

        return self.current_modes()["text"]

    def current_probe_interval_seconds(self) -> int:
        """返回当前嗅探周期；未配置或越界时回退默认值。"""

        record = self._settings.get()
        if record is None:
            return DEFAULT_PROBE_INTERVAL_SECONDS
        value = record.probe_interval_seconds
        if not MIN_PROBE_INTERVAL_SECONDS <= value <= MAX_PROBE_INTERVAL_SECONDS:
            return DEFAULT_PROBE_INTERVAL_SECONDS
        return value

    def view(self) -> dict:
        """返回管理视图。"""

        record = self._settings.get()
        return {
            "modes": self.current_modes(),
            "probe_interval_seconds": self.current_probe_interval_seconds(),
            "updated_at": record.updated_at.isoformat() if record is not None and record.updated_at else None,
        }

    def update(self, payload: dict) -> dict:
        """按请求类型切换模式，并按需更新嗅探周期。"""

        values: dict = {}
        modes_payload = payload.get("modes")
        if modes_payload is not None:
            if not isinstance(modes_payload, dict):
                raise ValidationError("不支持的监控模式")
            unknown_types = [request_type for request_type in modes_payload if request_type not in MONITOR_MODE_TYPES]
            if unknown_types:
                raise ValidationError("不支持的请求类型")
            modes = self.current_modes()
            for request_type in MONITOR_MODE_TYPES:
                if modes_payload.get(request_type) is None:
                    continue
                mode = str(modes_payload[request_type])
                if mode not in MONITOR_MODES:
                    raise ValidationError("不支持的监控模式")
                if request_type != "text" and mode == MONITOR_MODE_PROBE:
                    raise ValidationError("仅文本类型支持嗅探模式")
                modes[request_type] = mode
            values.update(
                {MODE_FIELD_BY_TYPE[request_type]: modes[request_type] for request_type in MONITOR_MODE_TYPES}
            )
        interval = payload.get("probe_interval_seconds")
        if interval is not None:
            if not isinstance(interval, int) or isinstance(interval, bool):
                raise ValidationError("嗅探周期必须是整数秒")
            if not MIN_PROBE_INTERVAL_SECONDS <= interval <= MAX_PROBE_INTERVAL_SECONDS:
                raise ValidationError("嗅探周期必须在 30 到 3600 秒之间")
            values["probe_interval_seconds"] = interval
        try:
            existing: MonitorTrafficSetting | None = self._settings.get()
            if existing is None:
                record = self._settings.create({**_default_mode_values(), **values})
            elif values:
                record = self._settings.update(existing, values)
            else:
                record = existing
            self._session.commit()
            self._settings.refresh(record)
        except Exception:
            self._session.rollback()
            raise
        return self.view()
