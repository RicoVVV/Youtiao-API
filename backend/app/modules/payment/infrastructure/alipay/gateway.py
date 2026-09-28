"""支付宝官方 Page Pay 网关适配器，负责 RSA2 签名、表单生成和通知验签。"""

import base64
import json
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from app.modules.payment.domain.config import AlipayOfficialRuntimeConfig
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding


class AlipayPageGateway:
    """支付宝电脑网站支付适配器，只处理支付宝协议，不处理订单和钱包。"""

    def __init__(self, config: AlipayOfficialRuntimeConfig) -> None:
        """绑定一份不可变配置；由支付应用服务在下单或回调时创建。"""
        self._config = config

    def build_order_form(self, order_no: str, pay_amount: Decimal, subject: str, return_url: str) -> dict[str, object]:
        """生成提交支付宝 `alipay.trade.page.pay` 的 HTML 表单数据。

        作用：组装支付宝页面支付参数，并在签名前写入本次订单的同步跳转地址。
        使用位置：由支付宝应用服务在本地订单创建后、持久化前调用。
        传入参数：order_no 为本地订单号；pay_amount 为冻结实付金额；subject 为商品名称；return_url 为支付完成后的同步跳转地址。
        返回参数：返回前端提交支付宝所需的网关地址、请求方法和已签名参数。
        """
        params = {
            "app_id": self._config.app_id,
            "method": "alipay.trade.page.pay",
            "format": "JSON",
            "return_url": return_url,
            "charset": "utf-8",
            "sign_type": "RSA2",
            "timestamp": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
            "version": "1.0",
            "notify_url": self._config.callback_url,
            "biz_content": json.dumps(
                {
                    "out_trade_no": order_no,
                    "total_amount": f"{pay_amount:.2f}",
                    "subject": subject,
                    "product_code": "FAST_INSTANT_TRADE_PAY",
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        }
        params["sign"] = self._sign(params)
        return {"action_type": "form_post", "gateway_url": self._config.gateway_url, "method": "POST", "params": params}

    def verify_callback(self, params: dict[str, str]) -> dict[str, str]:
        """验签支付宝异步通知并返回结算字段；非法通知抛出 ValueError。"""
        signature = params.get("sign", "")
        if not signature or not self._verify(params, signature):
            raise ValueError("支付宝回调签名无效")
        if params.get("app_id") != self._config.app_id:
            raise ValueError("支付宝回调应用不匹配")
        if self._config.seller_id and params.get("seller_id") != self._config.seller_id:
            raise ValueError("支付宝回调卖家不匹配")
        for key in ("out_trade_no", "trade_no", "total_amount", "trade_status"):
            if not params.get(key):
                raise ValueError("支付宝回调缺少订单字段")
        try:
            amount = Decimal(params["total_amount"])
        except InvalidOperation as exc:
            raise ValueError("支付宝回调金额无效") from exc
        if amount <= 0 or f"{amount:.2f}" != params["total_amount"]:
            raise ValueError("支付宝回调金额格式无效")
        return params

    def _sign(self, params: dict[str, str]) -> str:
        """按支付宝规则排序字段并使用应用私钥 RSA2 签名。"""
        content = "&".join(f"{k}={v}" for k, v in sorted(params.items()) if v and k not in {"sign", "sign_type"})
        key = serialization.load_pem_private_key(self._config.private_key.encode(), password=None)
        return base64.b64encode(key.sign(content.encode(), padding.PKCS1v15(), hashes.SHA256())).decode()

    def _verify(self, params: dict[str, str], signature: str) -> bool:
        """用支付宝公钥验证通知签名。"""
        content = "&".join(f"{k}={v}" for k, v in sorted(params.items()) if v and k not in {"sign", "sign_type"})
        try:
            key = serialization.load_pem_public_key(self._config.public_key.encode())
            key.verify(base64.b64decode(signature), content.encode(), padding.PKCS1v15(), hashes.SHA256())
            return True
        except Exception:
            return False
