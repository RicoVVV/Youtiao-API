"""请求语言解析与请求级语言绑定。

语言来源优先级：显式请求头 ``X-Locale`` > 标准请求头 ``Accept-Language`` > 默认中文。
显式头必须经白名单归一后才生效，避免客户端用任意字符串控制服务端输出。
"""

from __future__ import annotations

from contextvars import ContextVar, Token

SUPPORTED_LOCALES: tuple[str, ...] = ("zh", "en")
DEFAULT_LOCALE: str = "zh"

LOCALE_HEADER = "X-Locale"
ACCEPT_LANGUAGE_HEADER = "Accept-Language"

_locale: ContextVar[str] = ContextVar("locale", default=DEFAULT_LOCALE)


def normalize_locale(value: str | None) -> str | None:
    """把语言标识归一为受支持的语言代码；不受支持时返回空值。

    接受 ``zh``、``zh-CN``、``zh_CN``、``EN`` 等写法，仅取主语言子标签。
    """

    if not value:
        return None
    primary = value.strip().lower().replace("_", "-").split("-")[0]
    return primary if primary in SUPPORTED_LOCALES else None


def parse_accept_language(value: str | None) -> str | None:
    """按 q 值降序解析 ``Accept-Language``，返回首个受支持的语言。

    ``q=0`` 表示明确拒绝，直接跳过；同 q 值时保持请求头中的原始顺序。
    """

    if not value:
        return None
    ranked: list[tuple[float, int, str]] = []
    for index, part in enumerate(value.split(",")):
        token, _, params = part.partition(";")
        quality = 1.0
        for param in params.split(";"):
            key, _, raw = param.partition("=")
            if key.strip().lower() == "q":
                try:
                    quality = float(raw.strip())
                except ValueError:
                    quality = 0.0
        candidate = normalize_locale(token)
        if candidate is not None and quality > 0:
            ranked.append((-quality, index, candidate))
    if not ranked:
        return None
    ranked.sort()
    return ranked[0][2]


def resolve_locale(explicit: str | None, accept_language: str | None) -> str:
    """解析本次请求应使用的语言，无法判定时回退默认语言。"""

    return normalize_locale(explicit) or parse_accept_language(accept_language) or DEFAULT_LOCALE


def get_locale() -> str:
    """返回当前请求绑定的语言。"""

    return _locale.get()


def set_locale(locale: str) -> Token[str]:
    """绑定当前请求的语言，返回用于还原的令牌。"""

    return _locale.set(locale)


def reset_locale(token: Token[str]) -> None:
    """还原绑定前的语言，避免请求间串味。"""

    _locale.reset(token)
