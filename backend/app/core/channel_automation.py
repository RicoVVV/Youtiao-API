"""渠道自动化运行配置：管理员可调的探测、自动禁用与自动重试策略。

管理员配置持久化在 ``system_settings``，本模块提供状态码语法解析、运行配置值对象与进程内缓存，
供 Provider 错误映射、健康探测与请求失败自动禁用共享，避免请求路径反复读库。
"""

import logging
import re
import threading
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

DEFAULT_AUTO_DISABLE_STATUS_CODES = "401,429"
DEFAULT_AUTO_RETRY_STATUS_CODES = "100-199,300-399,401-407,409-499,500-503,505-523,525-599"
ALWAYS_NON_RETRYABLE_STATUS_CODES = frozenset({504, 524})
"""无论管理员如何配置都不自动重试的状态码。"""

DEFAULT_AUTO_DISABLE_KEYWORDS = "\n".join(
    (
        "Your credit balance is too low",
        "This organization has been disabled.",
        "You exceeded your current quota",
        "Permission denied",
        "The security token included in the request is invalid",
        "Operation not allowed",
        "Your account is not authorized",
        "unknown provider for model",
        "The usage limit has been reached",
        "预扣费额度失败",
        "Insufficient account balance",
        "no auth available",
    )
)

_STATUS_CODE_PATTERN = re.compile(r"^(\d{3})(?:-(\d{3}))?$")
_NORMALIZED_COMMA = "，"


def parse_status_code_spec(spec: str) -> frozenset[int]:
    """把 ``401,429`` 或 ``400-499`` 形式的状态码配置展开为状态码集合。

    支持中英文逗号分隔、首尾空白与空段；单个状态码必须是 100-599，范围要求起点不大于终点。
    格式不合法时抛出 ``ValueError``，由调用方转换为业务校验错误。
    """

    codes: set[int] = set()
    for raw_part in spec.replace(_NORMALIZED_COMMA, ",").split(","):
        part = raw_part.strip()
        if not part:
            continue
        matched = _STATUS_CODE_PATTERN.match(part)
        if matched is None:
            raise ValueError(f"状态码格式不合法：{part}")
        start = int(matched.group(1))
        end = int(matched.group(2) or start)
        if not 100 <= start <= 599 or not 100 <= end <= 599 or start > end:
            raise ValueError(f"状态码超出范围：{part}")
        codes.update(range(start, end + 1))
    return frozenset(codes)


def parse_keyword_text(text: str) -> tuple[str, ...]:
    """把多行关键词配置拆成去重后的关键词元组，忽略空行。"""

    keywords: list[str] = []
    seen: set[str] = set()
    for line in text.splitlines():
        keyword = line.strip()
        if not keyword:
            continue
        normalized = keyword.casefold()
        if normalized in seen:
            continue
        seen.add(normalized)
        keywords.append(keyword)
    return tuple(keywords)


def resolve_status_code(code: str | None, status_code: int | None) -> int | None:
    """解析错误对应的 HTTP 状态码；适配器已提供时优先使用，否则从三位数字错误码推导。"""

    if status_code is not None:
        return status_code
    if code is not None and code.isdigit() and len(code) == 3:
        return int(code)
    return None


@dataclass(frozen=True, slots=True)
class ChannelAutomationConfig:
    """一次运行期内生效的渠道自动化策略快照。"""

    probe_enabled: bool = False
    probe_interval_seconds: int = 60
    probe_timeout_seconds: int = 5
    auto_disable_enabled: bool = False
    auto_enable_enabled: bool = True
    auto_disable_status_codes: frozenset[int] = field(
        default_factory=lambda: parse_status_code_spec(DEFAULT_AUTO_DISABLE_STATUS_CODES)
    )
    auto_retry_status_codes: frozenset[int] = field(
        default_factory=lambda: parse_status_code_spec(DEFAULT_AUTO_RETRY_STATUS_CODES)
    )
    auto_disable_keywords: tuple[str, ...] = field(
        default_factory=lambda: parse_keyword_text(DEFAULT_AUTO_DISABLE_KEYWORDS)
    )


DEFAULT_CHANNEL_AUTOMATION_CONFIG = ChannelAutomationConfig()

_cached_config: ChannelAutomationConfig | None = None
_cache_lock = threading.Lock()


def get_channel_automation_config() -> ChannelAutomationConfig:
    """读取进程内缓存的管理员配置；尚未加载时使用与旧行为一致的默认值。"""

    with _cache_lock:
        return _cached_config or DEFAULT_CHANNEL_AUTOMATION_CONFIG


def set_channel_automation_config(config: ChannelAutomationConfig) -> None:
    """更新进程内缓存；管理员保存设置或后台任务刷新配置时调用。"""

    global _cached_config
    with _cache_lock:
        _cached_config = config
