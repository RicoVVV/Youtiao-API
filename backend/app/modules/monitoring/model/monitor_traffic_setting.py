"""分组监控数据模式配置 ORM 模型，单行保存管理员选择的统一监控模式。

``real`` 展示用户真实请求，``probe`` 展示平台主动发送的最小文本嗅探结果。
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Column, DateTime, Integer, String, func
from sqlmodel import Field

from app.core.database import SQLModelBase

MONITOR_TRAFFIC_SETTING_ID = UUID(int=5)
"""分组监控数据模式配置固定使用的主键，保证配置表始终只有一行。"""

MONITOR_MODE_REAL = "real"
MONITOR_MODE_PROBE = "probe"
MONITOR_MODES = (MONITOR_MODE_REAL, MONITOR_MODE_PROBE)

MONITOR_MODE_TYPES = ("text", "image", "video")
"""监控模式按请求类型分别配置；嗅探仅对文本生效。"""

MODE_FIELD_BY_TYPE = {
    "text": "text_mode",
    "image": "image_mode",
    "video": "video_mode",
}

DEFAULT_MONITOR_MODES = {
    "text": MONITOR_MODE_PROBE,
    "image": MONITOR_MODE_REAL,
    "video": MONITOR_MODE_REAL,
}
"""默认文本走嗅探，图片与视频走真实请求。"""

DEFAULT_PROBE_INTERVAL_SECONDS = 60
MIN_PROBE_INTERVAL_SECONDS = 30
MAX_PROBE_INTERVAL_SECONDS = 3600
"""嗅探模式下两次分组文本探测之间的最小间隔范围与默认值。

下限取 30 秒与默认系统任务调度周期对齐，避免配置值小于实际调度粒度。
"""


class MonitorTrafficSetting(SQLModelBase, table=True):
    """保存按请求类型区分的监控数据模式与嗅探周期。"""

    __tablename__ = "monitor_traffic_settings"

    id: UUID = Field(default=MONITOR_TRAFFIC_SETTING_ID, primary_key=True, description="配置主键，固定值")
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now(), comment="创建时间"),
    )
    updated_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(), comment="更新时间"
        ),
    )
    text_mode: str = Field(
        default=DEFAULT_MONITOR_MODES["text"],
        sa_column=Column(
            String(16),
            nullable=False,
            server_default=DEFAULT_MONITOR_MODES["text"],
            comment="文本请求数据模式：real 或 probe",
        ),
    )
    image_mode: str = Field(
        default=DEFAULT_MONITOR_MODES["image"],
        sa_column=Column(
            String(16),
            nullable=False,
            server_default=DEFAULT_MONITOR_MODES["image"],
            comment="图片请求数据模式：固定 real",
        ),
    )
    video_mode: str = Field(
        default=DEFAULT_MONITOR_MODES["video"],
        sa_column=Column(
            String(16),
            nullable=False,
            server_default=DEFAULT_MONITOR_MODES["video"],
            comment="视频请求数据模式：固定 real",
        ),
    )
    probe_interval_seconds: int = Field(
        default=DEFAULT_PROBE_INTERVAL_SECONDS,
        sa_column=Column(
            Integer,
            nullable=False,
            server_default=str(DEFAULT_PROBE_INTERVAL_SECONDS),
            comment="嗅探模式下两次分组文本探测之间的间隔秒数",
        ),
    )
