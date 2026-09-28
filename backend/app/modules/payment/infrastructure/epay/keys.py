"""易支付 V2 RSA 密钥加载，兼容 PEM 与商户后台展示的 Base64 DER 格式。"""

import base64
from binascii import Error as BinasciiError

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def load_merchant_private_key(key_text: str) -> rsa.RSAPrivateKey:
    """加载商户 RSA 私钥。

    作用：支持管理员直接粘贴易支付后台提供的 PEM 或无头尾 Base64 密钥文本。
    使用位置：易支付配置校验和页面支付签名调用。
    传入参数：key_text 为商户私钥文本。
    返回参数：返回已解析的 RSA 私钥；格式不合法时抛出 ValueError。
    """
    try:
        key = serialization.load_pem_private_key(key_text.encode(), password=None)
    except (TypeError, ValueError):
        key = serialization.load_der_private_key(_decode_base64_der(key_text), password=None)
    if not isinstance(key, rsa.RSAPrivateKey):
        raise ValueError("易支付商户私钥必须是 RSA 格式")
    return key


def load_platform_public_key(key_text: str) -> rsa.RSAPublicKey:
    """加载易支付平台 RSA 公钥。

    作用：支持管理员直接粘贴易支付后台提供的 PEM 或无头尾 Base64 公钥文本。
    使用位置：易支付配置校验和异步通知验签调用。
    传入参数：key_text 为平台公钥文本。
    返回参数：返回已解析的 RSA 公钥；格式不合法时抛出 ValueError。
    """
    try:
        key = serialization.load_pem_public_key(key_text.encode())
    except (TypeError, ValueError):
        key = serialization.load_der_public_key(_decode_base64_der(key_text))
    if not isinstance(key, rsa.RSAPublicKey):
        raise ValueError("易支付平台公钥必须是 RSA 格式")
    return key


def _decode_base64_der(key_text: str) -> bytes:
    """去除空白后解码后台展示的 Base64 DER 密钥文本。"""
    normalized = "".join(key_text.split())
    if not normalized:
        raise ValueError("易支付 RSA 密钥不能为空")
    try:
        return base64.b64decode(normalized, validate=True)
    except (BinasciiError, ValueError) as exc:
        raise ValueError("易支付 RSA 密钥格式无效") from exc
