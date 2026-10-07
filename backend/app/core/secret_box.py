"""从 JWT 签名密钥派生各用途的 Fernet 加密密钥，用于加密数据库中保存的第三方凭据。

不同用途通过 HKDF 的 info 参数隔离，派生出的密钥互不相同；更换 JWT_SIGNING_KEY 后，
已保存的密文将无法解密，需要管理员在后台重新填写对应凭据。
"""

import base64

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

SMTP_CONFIG_PURPOSE = "avrouter/smtp-config"


def derive_fernet(master_key: str, purpose: str) -> Fernet:
    """按用途从主密钥派生 Fernet 实例。"""
    derived = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=purpose.encode()).derive(master_key.encode())
    return Fernet(base64.urlsafe_b64encode(derived))
