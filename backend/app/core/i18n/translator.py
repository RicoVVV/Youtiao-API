"""响应文案翻译入口。

翻译以中文原文为键：业务层继续按中文书写消息，由本模块在响应出口统一转换为目标语言。
未收录的中文原文或目标语言为中文时原样返回，保证任何遗漏都不会导致请求失败。

运行期拼接的文案（``f-string`` 与 ``str(exc)`` 透传）无法作为静态键命中，
改由业务层在 ``raise`` 时携带稳定 ``code`` 与 ``params``，按 ``CODE_MESSAGES`` 模板渲染。
模板渲染失败时同样回退原文，不抛异常。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.core.i18n.catalog import CODE_MESSAGES, MESSAGES_EN
from app.core.i18n.locales import DEFAULT_LOCALE, get_locale


def translate(
    message: str,
    locale: str | None = None,
    *,
    code: str | None = None,
    params: Mapping[str, Any] | None = None,
) -> str:
    """把中文响应文案翻译为目标语言；未收录或无法渲染时返回原文。

    参数：
        message: 业务层原始中文文案。
        locale: 目标语言；缺省时读取当前请求绑定的语言。
        code: 稳定业务码，用于命中 ``CODE_MESSAGES`` 模板。
        params: 模板占位符取值。
    返回：
        目标语言文案。中文、空串、未收录的文案以及模板渲染失败均返回原文。
    """

    if not message:
        return message
    if (locale or get_locale()) == DEFAULT_LOCALE:
        return message
    if code is not None:
        rendered = render_code_message(code, params)
        if rendered is not None:
            return rendered
    return MESSAGES_EN.get(message, message)


def render_code_message(code: str, params: Mapping[str, Any] | None = None) -> str | None:
    """按 ``code`` 与 ``params`` 渲染英文模板；无模板或渲染失败时返回空值。"""

    template = CODE_MESSAGES.get(code)
    if template is None:
        return None
    try:
        return template.format(**params) if params else template.format()
    except (KeyError, IndexError, ValueError):
        # 占位符缺失或取值非法时不暴露内部细节，交由调用方回退中文原文。
        return None


def translate_error(error: Exception, locale: str | None = None) -> str:
    """翻译业务异常：优先按 ``code`` 与 ``params`` 渲染，否则按中文原文查表。

    ``locale`` 传入时固定使用该语言（协议面统一英文），缺省时读取当前请求绑定。
    """

    return translate(
        str(error),
        locale,
        code=getattr(error, "code", None),
        params=getattr(error, "params", None),
    )
