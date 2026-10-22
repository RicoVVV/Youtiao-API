"""渠道失败判定：区分上游侧故障与请求侧、配置侧错误。"""

from app.modules.providers.contracts import ProviderError

_UPSTREAM_FAILURE_CODES = frozenset({"timeout", "network", "invalid_response", "upstream_unavailable"})


def is_channel_failure(error: ProviderError) -> bool:
    """判断本次上游异常是否应计入渠道熔断与权重衰减。

    超时、网络错误、无效响应与可重试的上游错误计入；请求契约、鉴权、余额不足、客户端取消与
    平台配置类错误不计入，避免用户请求把渠道打成熔断。
    """

    return bool(error.retryable or error.code in _UPSTREAM_FAILURE_CODES)
