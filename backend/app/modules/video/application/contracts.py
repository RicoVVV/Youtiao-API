"""视频应用层输入与任务安全投影契约。

本模块定义应用服务与 HTTP、管理端等适配层之间传递的不可变数据结构，不依赖 FastAPI 或 Pydantic；
请求动态字段保持字典形式，由版本化模型配置负责业务校验。
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class VideoContentSource:
    """表示视频成品内容的交付来源。

    外部直链交付时只给出 ``redirect_url``，由接入层重定向到上游地址；平台本地化成品时给出 ``content_type``
    与惰性 ``chunks``，接入层按字节流下发。两类来源互斥，且都不包含渠道配置或认证数据。
    """

    redirect_url: str | None = None
    content_type: str | None = None
    chunks: AsyncIterator[bytes] | None = None


@dataclass(frozen=True, slots=True)
class VideoTaskData:
    """表示可安全交给外部适配层转换的视频任务投影。

    参数字段包含任务标识、生命周期、进度、时间、媒体地址及已脱敏错误信息。
    返回值由应用服务创建后供 HTTP DTO 映射使用；实例不可变且不包含渠道配置、上游请求或认证数据。
    """

    id: str
    model: str
    status: str
    progress: float
    created_at: datetime
    completed_at: datetime | None
    result_url: str | None
    error: dict[str, Any] | None


@dataclass(frozen=True, slots=True)
class OpenAIVideoData:
    id: str
    model: str
    status: str
    progress: int
    created_at: datetime
    result_url: str | None
    error: dict[str, str] | None
    cost: str | None
    balance: str | None
    reference_tokens: str | None
