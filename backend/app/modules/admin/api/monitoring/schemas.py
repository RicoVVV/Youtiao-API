"""管理员分组监控接口 DTO。"""

import re
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

AlertStatusValue = Literal["pending", "open", "resolved", "acknowledged", "ignored"]
AlertMetricValue = Literal[
    "success_rate",
    "average_duration_ms",
    "average_first_token_ms",
    "cpu_usage",
    "memory_usage",
    "swap_usage",
    "disk_usage",
]
AlertScopeValue = Literal["group", "server"]
RequestTypeValue = Literal["text", "image", "video"]

MOBILE_PATTERN = re.compile(r"1[3-9]\d{9}")
"""告警推送 @ 的手机号格式，仅接受 11 位中国大陆手机号。"""

MAX_AT_MOBILES = 20
"""单条规则最多配置的 @ 手机号数量。"""


class AdminGroupMonitorListQuery(BaseModel):
    """查询全部分组监控指标时的筛选条件。"""

    model_config = ConfigDict(extra="forbid")

    group_id: int | None = Field(default=None, description="可选，仅返回指定分组的指标")


class AdminGroupMonitorTrendQuery(BaseModel):
    """查询分组监控趋势时的筛选条件。"""

    model_config = ConfigDict(extra="forbid")

    group_id: int = Field(description="待查询的 Token 分组标识")
    request_type: RequestTypeValue | None = Field(default=None, description="可选，请求类型")
    hours: int = Field(default=24, ge=1, le=168, description="统计时长，最大 168 小时")


class AdminChannelMonitorQuery(BaseModel):
    """查询渠道维度运维指标时的筛选条件。"""

    model_config = ConfigDict(extra="forbid")

    group_id: int | None = Field(default=None, description="可选，仅返回指定分组下的渠道指标")


class AdminAlertListQuery(BaseModel):
    """分页查询告警记录时的筛选条件。"""

    model_config = ConfigDict(extra="forbid")

    status: AlertStatusValue | None = Field(default=None, description="告警状态")
    group_id: int | None = Field(default=None, description="所属 Token 分组标识")
    channel_id: UUID | None = Field(default=None, description="所属渠道标识")
    metric: AlertMetricValue | None = Field(default=None, description="指标类别，优先于告警范围")
    scope: AlertScopeValue | None = Field(
        default=None, description="告警范围：group 为分组业务告警，server 为服务器资源告警"
    )
    hours: int | None = Field(default=None, ge=1, le=720, description="仅返回最近若干小时内评估过的告警")
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class AdminAlertStatusUpdateRequest(BaseModel):
    """人工处置告警时提交的目标标识与目标状态。"""

    alert_id: UUID
    status: Literal["acknowledged", "ignored"]


class AdminAlertRuleUpdateRequest(BaseModel):
    """新增或更新告警阈值规则时提交的字段。

    不传 ``group_id`` 或传 ``null`` 都表示更新全局默认规则；显式传 ``null`` 的阈值表示不再评估该指标。
    非空字段（``enabled``、``min_sample_count``、``consecutive_hits``、``at_mobiles``、``at_all``）不接受 ``null``，
    它们的默认值仅用于满足类型定义，实际取值以「字段是否传入」为准（路由使用 ``exclude_unset``）。
    ``at_mobiles`` 为空表示沿用全局默认规则的 @ 目标。
    """

    group_id: int | None = None
    enabled: bool = True
    success_rate_min: Decimal | None = Field(default=None, ge=0, le=1, max_digits=6, decimal_places=4)
    avg_duration_ms_max: int | None = Field(default=None, ge=1, le=86400000)
    avg_first_token_ms_max: int | None = Field(default=None, ge=1, le=86400000)
    min_sample_count: int = Field(default=20, ge=1, le=1000000)
    consecutive_hits: int = Field(default=2, ge=1, le=288)
    at_mobiles: str = Field(default="", max_length=512, description="告警推送 @ 的手机号，逗号分隔")
    at_all: bool = Field(default=False, description="告警推送是否 @ 所有人")

    @field_validator("at_mobiles")
    @classmethod
    def _normalize_at_mobiles(cls, value: str) -> str:
        """校验并规范化 @ 手机号列表：去空白、去重、限制数量。"""

        mobiles = [item.strip() for item in value.split(",") if item.strip()]
        invalid = next((item for item in mobiles if not MOBILE_PATTERN.fullmatch(item)), None)
        if invalid is not None:
            raise ValueError(f"手机号格式不正确：{invalid}")
        unique = list(dict.fromkeys(mobiles))
        if len(unique) > MAX_AT_MOBILES:
            raise ValueError(f"@ 手机号最多 {MAX_AT_MOBILES} 个")
        return ",".join(unique)


class AdminAlertRuleDeleteRequest(BaseModel):
    """删除分组覆盖阈值规则时提交的目标分组标识。"""

    group_id: int


class AdminNotificationUpdateRequest(BaseModel):
    """更新钉钉推送配置时提交的字段。

    未提供的字段保持原值，传空字符串表示清空；字段均为非空配置，
    传 ``null`` 会返回 422，避免把空值写进非空列。默认值仅用于满足类型定义。
    分组业务告警与服务器资源告警的推送开关互相独立。
    """

    notify_group_alerts: bool = False
    notify_resource_alerts: bool = False
    webhook_url: str = Field(default="", max_length=2048)
    sign_secret: str = Field(default="", max_length=512)
    keyword: str = Field(default="", max_length=64)
    timeout_seconds: int = Field(default=10, ge=1, le=60)
    silence_minutes: int = Field(default=30, ge=0, le=1440)
    notify_on_resolved: bool = False


class AdminServerMetricTrendQuery(BaseModel):
    """查询服务器资源趋势时的筛选条件。"""

    model_config = ConfigDict(extra="forbid")

    hours: int = Field(default=6, ge=1, le=72, description="统计时长，最大 72 小时")


class AdminResourceRuleUpdateRequest(BaseModel):
    """更新服务器资源告警阈值时提交的字段。

    未提供的字段保持原值；显式传 ``null`` 的阈值表示不再评估该指标。
    非空字段（``enabled``、``consecutive_hits``）不接受 ``null``，
    它们的默认值仅用于满足类型定义，实际取值以「字段是否传入」为准（路由使用 ``exclude_unset``）。
    """

    enabled: bool = True
    cpu_usage_max: Decimal | None = Field(default=None, ge=0, le=100, max_digits=7, decimal_places=3)
    memory_usage_max: Decimal | None = Field(default=None, ge=0, le=100, max_digits=7, decimal_places=3)
    swap_usage_max: Decimal | None = Field(default=None, ge=0, le=100, max_digits=7, decimal_places=3)
    disk_usage_max: Decimal | None = Field(default=None, ge=0, le=100, max_digits=7, decimal_places=3)
    consecutive_hits: int = Field(default=3, ge=1, le=1440)
