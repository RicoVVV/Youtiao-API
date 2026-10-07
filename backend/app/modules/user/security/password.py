"""用户密码安全原语，仅负责 Argon2 摘要生成和验证。"""

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

password_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    """生成 Argon2 密码摘要，调用方不得记录传入明文。"""

    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """校验密码摘要，失败统一返回 False 以隐藏账户存在性。"""

    try:
        return password_hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False
