"""统一 JSON 响应信封，确保响应体状态码与 HTTP 状态保持一致。"""

from typing import Any


def response_body(status_code: int, message: str, data: Any, request_id: str | None) -> dict[str, Any]:
    """构造包含状态码、消息、数据和请求关联标识的统一响应体。"""

    return {
        "code": status_code,
        "message": message,
        "data": data,
        "request_id": request_id,
    }
