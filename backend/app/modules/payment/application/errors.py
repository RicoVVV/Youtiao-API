"""支付应用层共享业务异常，统一定义各支付渠道可安全返回给接口层的错误类型。"""

from app.core.errors import ApplicationError, NotFoundError


class PaymentBusinessError(ApplicationError):
    """支付业务规则不满足时抛出的安全错误，不包含底层异常细节。"""


class PaymentDisabledError(PaymentBusinessError):
    """支付开关关闭或运行时配置不可用时抛出的业务错误。"""


class PaymentProviderUnavailableError(PaymentBusinessError):
    """第三方支付服务暂时不可用时抛出的可重试错误。"""


class PaymentAmountInvalidError(PaymentBusinessError):
    """用户提交的充值金额不符合当前支付定价规则时抛出。"""


class PaymentOrderNotFoundError(PaymentBusinessError, NotFoundError):
    """当前用户无权访问或订单不存在时抛出，避免泄露订单归属。"""


class PaymentCallbackValidationError(PaymentBusinessError):
    """支付平台回调的签名或必要字段不合法时抛出。"""


class PaymentCallbackProcessingError(PaymentBusinessError):
    """支付平台回调暂时无法处理、可由平台重试时抛出。"""
