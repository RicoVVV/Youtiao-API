"""流式 HTTP 响应的传输层保护。"""

import inspect
from collections.abc import AsyncIterator

from fastapi import Request
from fastapi.responses import StreamingResponse

_STREAM_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
}


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
    try:
        async for chunk in stream:
            if await request.is_disconnected():
                return
            yield chunk
    finally:
        close = getattr(stream, "aclose", None)
        if close is not None:
            result = close()
            if inspect.isawaitable(result):
                await result
