"""长期 Token 安全原语，负责生成随机明文和展示前缀。"""

import secrets


def generate_token() -> str:
    """生成用于长期 Bearer 鉴权的完整随机明文 Token。"""

    return f"sk-{secrets.token_urlsafe(32)}"
