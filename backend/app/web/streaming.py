"""流式 HTTP 响应的传输层保护。"""

import inspect
import time
from collections.abc import AsyncIterator

from fastapi import Request
from fastapi.responses import StreamingResponse

_STREAM_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
}
_DISCONNECT_CHECK_SECONDS = 1.0
"""断连检测间隔：每个 chunk 都轮询 receive 会在千级并发流下产生大量无谓开销。"""


def streaming_response(
    request: Request,
    stream: AsyncIterator[bytes],
    content_type: str,
) -> StreamingResponse:
    return StreamingResponse(
        _stop_on_downstream_disconnect(request, stream),
        media_type=content_type,
        headers=_STREAM_HEADERS,
    )


async def _stop_on_downstream_disconnect(request: Request, stream: AsyncIterator[bytes]) -> AsyncIterator[bytes]:
    # 首个 chunk 立即检测一次，之后按固定间隔节流，避免每个 chunk 都轮询 receive。
    last_check = 0.0
    try:
        async for chunk in stream:
            now = time.monotonic()
            if now - last_check >= _DISCONNECT_CHECK_SECONDS:
                last_check = now
                if await request.is_disconnected():
                    return
            yield chunk
    finally:
        close = getattr(stream, "aclose", None)
        if close is not None:
            result = close()
            if inspect.isawaitable(result):
                await result
