"""响应文案的请求级本地化能力。

对外只暴露 ``translate`` 与语言解析、绑定的最小接口；目录数据由 ``catalog`` 私有持有。
"""

from app.core.i18n.locales import (
    ACCEPT_LANGUAGE_HEADER,
    DEFAULT_LOCALE,
    LOCALE_HEADER,
    SUPPORTED_LOCALES,
    get_locale,
    normalize_locale,
    parse_accept_language,
    reset_locale,
    resolve_locale,
    set_locale,
)
from app.core.i18n.translator import render_code_message, translate, translate_error

__all__ = [
    "ACCEPT_LANGUAGE_HEADER",
    "DEFAULT_LOCALE",
    "LOCALE_HEADER",
    "SUPPORTED_LOCALES",
    "get_locale",
    "normalize_locale",
    "parse_accept_language",
    "render_code_message",
    "reset_locale",
    "resolve_locale",
    "set_locale",
    "translate",
    "translate_error",
]
