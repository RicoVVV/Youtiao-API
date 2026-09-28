"""应用、Worker 与容器服务共享的运行配置，并集中校验支付等运行参数。"""

import logging
from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEVELOPMENT_JWT_SIGNING_KEY = "development-jwt-signing-key-change-me"
_DEVELOPMENT_REFRESH_TOKEN_PEPPER = "development-refresh-pepper-change-me"
_FORBIDDEN_SECRET_VALUES = {"change-me", "changeme", "placeholder", "example", "secret", "test"}
_BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """读取 API、数据库、Redis 与 Provider 的运行配置。

    所有字段优先由环境变量或 ``.env`` 提供；密钥字段仅在进程内使用，禁止输出到日志。
    """

    app_env: str = "development"
    log_level: str = "INFO"
    log_format: str = "text"
    database_url: str
    database_async_url: str | None = None
    jwt_signing_key: str = _DEVELOPMENT_JWT_SIGNING_KEY
    jwt_issuer: str = "video-api"
    jwt_audience: str = "video-api-clients"
    refresh_token_pepper: str = _DEVELOPMENT_REFRESH_TOKEN_PEPPER
    access_token_minutes: int = Field(default=15, ge=1)
    refresh_token_days: int = Field(default=30, ge=1, le=90)
    auth_cookie_secure: bool = False
    auth_cookie_samesite: str = "lax"
    auth_cookie_domain: str | None = None
    cors_allow_origins: list[str] = Field(default_factory=list)
    public_base_url: str = ""
    """平台对外可访问的基础地址，用于生成成品下载等公开绝对地址；留空时仅返回相对路径。"""

    auth_redis_url: str = "redis://localhost:6379/2"
    auth_rate_limit_window_seconds: int = Field(default=60, ge=1, le=3600)
    auth_login_rate_limit: int = Field(default=30, ge=1, le=1000)
    auth_refresh_rate_limit: int = Field(default=20, ge=1, le=1000)
    auth_invalid_api_key_rate_limit: int = Field(default=20, ge=1, le=1000)
    auth_redis_circuit_breaker_seconds: int = Field(default=5, ge=1, le=60)
    system_task_scheduler_interval_seconds: int = Field(default=30, ge=1)
    system_task_lock_ttl_seconds: int = Field(default=60, ge=1)
    database_pool_size: int = Field(default=16, ge=1)
    database_max_overflow: int = Field(default=4, ge=0)
    database_async_pool_size: int = Field(default=36, ge=1)
    database_async_max_overflow: int = Field(default=6, ge=0)
    database_pool_timeout_seconds: int = Field(default=10, ge=1)
    database_pool_recycle_seconds: int = Field(default=1800, ge=1)
    http_max_connections: int = Field(default=32, ge=1)
    http_max_keepalive_connections: int = Field(default=16, ge=0)
    provider_read_timeout_seconds: int = Field(default=1800, ge=1)
    video_task_timeout_seconds: int = Field(default=86400, ge=1)
    """视频任务从成功提交至上游起的业务超时秒数。"""

    video_maintenance_batch_size: int = Field(default=100, ge=1, le=1000)
    """每次补偿扫描最多处理的任务数量。"""
    video_result_storage_dir: Path = _BACKEND_ROOT / "data" / "video-results"
    video_result_retention_hours: int = Field(default=12, ge=1)
    video_result_download_retry_seconds: int = Field(default=300, ge=1)
    video_material_download_timeout_seconds: int = Field(default=30, ge=1)
    """单个输入素材下载连接与读取的超时秒数。"""

    video_material_max_redirects: int = Field(default=3, ge=0, le=10)
    """输入素材下载允许的最大重定向次数，每次重定向都会重新校验目标地址。"""

    video_material_max_bytes: int = Field(default=209715200, ge=1)
    """单个输入素材允许的最大字节数，超过后立即中断下载并拒绝请求。"""

    video_material_max_video_seconds: int = Field(default=1200, ge=1)
    """单个输入视频允许的最大实测时长秒数。"""

    video_material_max_image_pixels: int = Field(default=64000000, ge=1)
    """单个输入图片允许的最大像素总数，用于阻断解码放大攻击。"""

    video_material_storage_dir: Path = _BACKEND_ROOT / "data" / "video-materials"
    """上传二进制素材的受控临时存储目录。"""

    video_material_retention_hours: int = Field(default=12, ge=1)
    """受控临时素材的保留小时数，到期后由维护任务删除落盘文件。"""

    # 支付配置存储在 options 表；此密钥仅用于加密和解密其中的敏感凭据。
    # 必须由部署环境注入 Fernet 密钥，禁止在源码中保留可用默认值：
    # 留空时支付配置的加解密会抛出 PaymentConfigEncryptionError，从而避免用泄露的密钥保护凭据。
    payment_config_encryption_key: str = ""
    # 支付回调对外基础地址；留空表示未配置，由部署环境按实际公网域名覆盖。
    payment_callback_base_url: str = ""
    payment_settings_sync_interval_seconds: int = Field(default=60, ge=5, le=3600)

    monitoring_snapshot_retention_days: int = Field(default=30, ge=1, le=365)
    """分组监控 5 分钟粒度快照的保留天数。"""

    monitoring_alert_retention_days: int = Field(default=90, ge=1, le=3650)
    """已结束的分组监控告警记录保留天数。"""

    monitoring_server_metric_retention_days: int = Field(default=7, ge=1, le=365)
    """服务器资源 1 分钟粒度快照的保留天数。"""

    monitoring_server_host_mode: bool = True
    """采集口径：True 读宿主 procfs 得到整机数据（生产使用），False 退化为采集本机（本地开发）。"""

    monitoring_server_proc_path: Path = Path("/host/proc")
    """宿主 procfs 路径，仅在 ``monitoring_server_host_mode`` 为真时使用。"""

    monitoring_server_disk_paths: list[str] = Field(default_factory=lambda: ["/host"])
    """纳入容量监控的路径列表，按当前采集口径下可见的挂载点视角填写。"""

    model_config = SettingsConfigDict(env_file=_BACKEND_ROOT / ".env", extra="ignore")

    @property
    def is_production(self) -> bool:
        return self.app_env.strip().lower() == "production"

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        """拒绝非开发环境弱密钥，避免认证配置失效。"""

        if self.log_level.upper() not in logging.getLevelNamesMapping():
            raise ValueError("LOG_LEVEL 必须是有效日志级别")
        if self.log_format not in {"json", "text"}:
            raise ValueError("LOG_FORMAT 必须是 json 或 text")
        if self.app_env.strip().lower() == "development":
            return self
        for value in (self.jwt_signing_key, self.refresh_token_pepper):
            normalized = value.strip().lower()
            # 空白、短值和常见占位符都无法提供足够的签名或摘要保护强度。
            if (
                value != value.strip()
                or len(value) < 32
                or normalized in _FORBIDDEN_SECRET_VALUES
                or value in {_DEVELOPMENT_JWT_SIGNING_KEY, _DEVELOPMENT_REFRESH_TOKEN_PEPPER}
            ):
                raise ValueError("非开发环境必须配置安全的 JWT 签名密钥和刷新令牌 Pepper")
        return self


@lru_cache
def get_settings() -> Settings:
    """返回进程内缓存的配置实例。

    返回：
        已经 Pydantic 校验的 ``Settings``。

    异常：
        配置缺失或字段不合法时抛出 Pydantic 校验异常并阻止服务启动。

    副作用：
        首次调用会读取环境与 ``.env``，后续调用复用同一配置快照。
    """

    return Settings()
