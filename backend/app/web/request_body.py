"""请求体读取上限。

公开协议面允许客户端提交包含长上下文或内联媒体的 JSON，但请求体必须挡在解析之前：
``request.json()`` 会把整个请求体一次性读入内存，数百 MB 的异常请求足以拖垮 worker。
本模块提供带体积上限的流式读取入口，超限立即返回 413，不再继续缓冲。
"""

from fastapi import HTTPException, Request, status

MAX_JSON_BODY_BYTES = 32 * 1024 * 1024
"""JSON 请求体上限；3 MB 级 coding-agent 上下文仍有充足余量，同时限制单请求内存放大。"""


async def read_json_body(request: Request, *, max_bytes: int = MAX_JSON_BODY_BYTES) -> bytes:
    """按上限流式读取原始请求体。

    参数：request 为当前请求；max_bytes 为允许的最大字节数。
    返回：完整请求体字节。
    异常：请求体超过上限时抛出 413，由全局异常处理器按协议面输出错误。
    """

    content_length = request.headers.get("content-length")
    if content_length and content_length.isdigit() and int(content_length) > max_bytes:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="请求体超出大小限制")
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > max_bytes:
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="请求体超出大小限制")
    return bytes(body)
