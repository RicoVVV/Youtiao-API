"""图片编辑上传的流式转发回归测试。

上游只接受定长 multipart，因此文件对象必须保持可 seek/可 stat，让 httpx 计算出 Content-Length，
而不是退化为 ``Transfer-Encoding: chunked``；同时确认文件内容确实按原样转发。
"""

import asyncio
import tempfile

import httpx
from app.modules.providers.contracts import ProviderUpload
from app.modules.providers.openai_compatible.adapter import OpenAICompatibleProvider


def test_edit_image_streams_file_as_fixed_length_multipart() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["content_length"] = request.headers.get("content-length")
        captured["transfer_encoding"] = request.headers.get("transfer-encoding")
        captured["body"] = request.content
        return httpx.Response(200, json={"created": 1, "data": []})

    provider = OpenAICompatibleProvider(
        "https://upstream.example.com",
        "test-key",
        transport=httpx.MockTransport(handler),
    )
    payload = b"png-bytes-" * 100
    with tempfile.SpooledTemporaryFile(max_size=1024) as handle:
        handle.write(payload)
        handle.seek(0)
        upload = ProviderUpload(
            field_name="image",
            filename="source.png",
            stream=handle,
            size=len(payload),
            content_type="image/png",
        )
        result = asyncio.run(provider.edit_image({"model": "gpt-image-1", "prompt": "make it blue"}, [upload]))

    body = captured["body"]
    assert result["data"] == []
    assert captured["transfer_encoding"] is None
    assert int(captured["content_length"]) == len(body)
    assert b'name="image[]"' in body
    assert payload in body
