"""渠道失败判定：区分上游侧故障与请求侧、配置侧错误，并给出自动禁用结论。"""

from app.core.channel_automation import get_channel_automation_config, resolve_status_code
from app.modules.providers.contracts import ProviderError

_UPSTREAM_FAILURE_CODES = frozenset({"timeout", "network", "invalid_response", "upstream_unavailable"})


def is_channel_failure(error: ProviderError) -> bool:
    """判断本次上游异常是否应计入渠道熔断与权重衰减。

    超时、网络错误、无效响应、可重试的上游错误以及管理员配置的自动重试状态码计入；请求契约、
    鉴权、余额不足、客户端取消与平台配置类错误不计入，避免用户请求把渠道打成熔断。
    """

    if error.is_user_error:
        return False
    config = get_channel_automation_config()
    status_code = resolve_status_code(error.code, error.status_code)
    return bool(
        error.retryable
        or error.code in _UPSTREAM_FAILURE_CODES
        or (status_code is not None and status_code in config.auto_retry_status_codes)
    )


def should_auto_disable_channel(error: ProviderError) -> bool:
    """按管理员配置的状态码与错误关键词判断本次失败是否应立即自动禁用渠道。"""

    if error.is_user_error:
        return False
    config = get_channel_automation_config()
    if not config.auto_disable_enabled:
        return False
    status_code = resolve_status_code(error.code, error.status_code)
    if status_code is not None and status_code in config.auto_disable_status_codes:
        return True
    if not config.auto_disable_keywords:
        return False
    message = str(error).casefold()
    return any(keyword.casefold() in message for keyword in config.auto_disable_keywords)
