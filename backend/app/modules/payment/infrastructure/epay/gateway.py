"""易支付 V2 页面跳转网关，负责 RSA 签名和异步通知验签。"""

import base64
import time
from decimal import Decimal, InvalidOperation

from app.modules.payment.domain.config import EpayRuntimeConfig
from app.modules.payment.infrastructure.epay.keys import load_merchant_private_key, load_platform_public_key
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding


class EpayPageGateway:
    """只处理易支付 V2 页面支付协议，不处理本地订单和钱包。"""

    def __init__(self, config: EpayRuntimeConfig) -> None:
        """绑定已校验的易支付配置。

        作用：为下单和回调验签提供同一份不可变渠道配置。
        使用位置：易支付应用服务创建网关适配器时调用。
        传入参数：config 为进程内易支付运行时配置。
        返回参数：无。
        """
        self._config = config

    def build_order_form(
        self, order_no: str, pay_amount: Decimal, subject: str, payment_method: str, return_url: str
    ) -> dict[str, object]:
        """生成易支付 V2 页面跳转表单。

        作用：构造并签名提交到易支付的页面支付参数。
        使用位置：易支付创建订单流程调用。
        传入参数：order_no 为本地订单号；pay_amount 为冻结实付金额；subject 为商品名称；payment_method 为易支付方式；return_url 为支付完成后的同步跳转地址。
        返回参数：返回前端可提交的网关地址、方法和参数，不包含私钥。
        """
        params = {
            "pid": self._config.partner_id,
            "type": payment_method,
            "out_trade_no": order_no,
            "notify_url": self._config.callback_url,
            "return_url": return_url,
            "name": subject,
            "money": f"{pay_amount:.2f}",
            "timestamp": str(int(time.time())),
            "sign_type": "RSA",
        }
        params["sign"] = self._sign(params)
        return {"action_type": "form_post", "gateway_url": self._config.gateway_url, "method": "POST", "params": params}

    def verify_callback(self, params: dict[str, str]) -> dict[str, str]:
        """验签并校验易支付成功通知的基础字段。

        作用：阻止伪造通知、过期通知和非易支付支付宝通知进入结算层。
        使用位置：易支付回调应用服务在锁定订单前调用。
        传入参数：params 为易支付回调的字符串参数表。
        返回参数：返回已完成协议校验的回调字段；失败时抛出 ValueError。
        """
        if params.get("pid") != self._config.partner_id or params.get("type") not in self._config.payment_methods:
            raise ValueError("易支付回调商户或支付类型不匹配")
        if params.get("sign_type") != "RSA" or not self._verify(params):
            raise ValueError("易支付回调签名无效")
        try:
            timestamp = int(params.get("timestamp", ""))
        except ValueError as exc:
            raise ValueError("易支付回调时间戳无效") from exc
        if abs(int(time.time()) - timestamp) > 300:
            raise ValueError("易支付回调已过期")
        for key in ("out_trade_no", "trade_no", "money", "trade_status"):
            if not params.get(key):
                raise ValueError("易支付回调缺少订单字段")
        try:
            amount = Decimal(params["money"])
        except InvalidOperation as exc:
            raise ValueError("易支付回调金额无效") from exc
        if amount <= 0 or f"{amount:.2f}" != params["money"]:
            raise ValueError("易支付回调金额格式无效")
        return params

    def _sign(self, params: dict[str, str]) -> str:
        """使用商户私钥生成 V2 RSA 签名。

        作用：将页面支付参数转换为易支付要求的 Base64 签名。
        使用位置：由 build_order_form 在返回表单前调用。
        传入参数：params 为待签名的非空支付参数。
        返回参数：返回 Base64 编码的 RSA 签名字符串。
        """
        content = _signing_content(params)
        key = load_merchant_private_key(self._config.private_key)
        signature = key.sign(content.encode(), padding.PKCS1v15(), hashes.SHA256())
        return base64.b64encode(signature).decode()

    def _verify(self, params: dict[str, str]) -> bool:
        """使用平台公钥验证 V2 回调签名。

        作用：确认通知确实由易支付平台签发且参数未被篡改。
        使用位置：由 verify_callback 在业务字段校验前调用。
        传入参数：params 为包含 `sign` 的回调参数。
        返回参数：签名有效返回 True，格式错误或验签失败返回 False。
        """
        try:
            signature = base64.b64decode(params.get("sign", ""), validate=True)
            key = load_platform_public_key(self._config.platform_public_key)
            key.verify(signature, _signing_content(params).encode(), padding.PKCS1v15(), hashes.SHA256())
            return True
        except Exception:
            return False


def _signing_content(params: dict[str, str]) -> str:
    """按易支付 V2 规则生成待签名字符串。

    作用：统一下单签名和回调验签使用的排序、过滤和拼接规则。
    使用位置：由 EpayPageGateway 的签名及验签方法调用。
    传入参数：params 为支付协议字段字典。
    返回参数：返回未 URL 编码的 `key=value&key=value` 字符串。
    """
    return "&".join(
        f"{key}={params[key]}" for key in sorted(params) if params[key] and key not in {"sign", "sign_type"}
    )
