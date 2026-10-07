"""公开协议路径判定。

公开协议面（OpenAI、Gemini、Anthropic、DashScope、火山方舟）的响应与错误必须保持各自协议形状，
因此这些路径不参与平台统一响应信封包装。判定集中在此模块，供访问日志中间件与异常映射共用。
"""


def is_anthropic_protocol_path(path: str) -> bool:
    """Anthropic Messages 原生协议面。"""

    return path.startswith("/v1/messages")


def is_openai_protocol_path(path: str) -> bool:
    """OpenAI 兼容协议面，Anthropic 原生路径不在此列。"""

    return path.startswith("/v1/") and not is_anthropic_protocol_path(path)


def is_gemini_protocol_path(path: str) -> bool:
    """Gemini 原生协议面。"""

    return path.startswith("/v1beta/")


def is_dashscope_protocol_path(path: str) -> bool:
    """千问 DashScope 原生 Generation 协议面。"""

    return path.startswith("/api/v1/services/aigc/")


def is_ark_protocol_path(path: str) -> bool:
    """火山方舟原生协议面。"""

    return path.startswith("/api/v3/")


def is_public_protocol_path(path: str) -> bool:
    """判断路径是否属于任一对外兼容协议面。"""

    return (
        is_openai_protocol_path(path)
        or is_anthropic_protocol_path(path)
        or is_gemini_protocol_path(path)
        or is_dashscope_protocol_path(path)
        or is_ark_protocol_path(path)
    )
