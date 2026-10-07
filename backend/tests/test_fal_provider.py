import asyncio
import json

import httpx
import pytest
from app.bootstrap.container import get_provider_registry, get_provider_template_registry
from app.modules.providers.contracts import CreateVideoCommand, ProviderError, ProviderTaskStatus
from app.modules.providers.fal.adapter import FalVideoProvider
from app.modules.providers.fal.templates import (
    FAL_MINIMAX_H3_MAX_IMAGE_TO_VIDEO_TEMPLATE,
    FAL_MINIMAX_H3_MAX_REFERENCE_TO_VIDEO_TEMPLATE,
    FAL_MINIMAX_H3_MAX_TEXT_TO_VIDEO_TEMPLATE,
)


def make_command(**overrides) -> CreateVideoCommand:
    request_body = {
        "model": "public-fal-model",
        "prompt": "一只猫在奔跑",
        "prompt_expansion_mode": "balanced",
        "seconds": 5,
        "resolution": "768P",
        "aspect_ratio": "16:9",
        "seed": 42,
    }
    request_body.update(overrides)
    return CreateVideoCommand(
        platform_task_id="platform-task",
        request_body=request_body,
    )


def test_fal_provider_submits_sync_request_with_key_authentication() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/minimax/h3-max/text-to-video"
        assert request.headers["authorization"] == "Key fal-key"
        assert request.headers["content-type"] == "application/json"
        assert json.loads(request.content) == {
            "prompt": "一只猫在奔跑",
            "prompt_expansion_mode": "balanced",
            "duration": 5,
            "resolution": "768P",
            "aspect_ratio": "16:9",
            "seed": 42,
            "enable_safety_checker": False,
            "sync_mode": False,
        }
        return httpx.Response(200, json={"video": {"url": "https://media.example.com/result.mp4"}})

    provider = FalVideoProvider(
        None,
        "fal-key",
        FAL_MINIMAX_H3_MAX_TEXT_TO_VIDEO_TEMPLATE.provider_config,
        transport=httpx.MockTransport(handler),
    )

    submission = asyncio.run(provider.submit(make_command()))

    assert submission.upstream_task_id == "https://media.example.com/result.mp4"
    assert submission.result_url == "https://media.example.com/result.mp4"
    assert submission.status is ProviderTaskStatus.succeeded


def test_fal_provider_forces_optional_switches_disabled() -> None:
    """客户端提交的 sync_mode 与 enable_safety_checker 一律被覆盖为 False。"""

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["sync_mode"] is False
        assert payload["enable_safety_checker"] is False
        return httpx.Response(200, json={"video": {"url": "https://media.example.com/result.mp4"}})

    provider = FalVideoProvider(
        None,
        "fal-key",
        FAL_MINIMAX_H3_MAX_TEXT_TO_VIDEO_TEMPLATE.provider_config,
        transport=httpx.MockTransport(handler),
    )

    asyncio.run(provider.submit(make_command(sync_mode=True, enable_safety_checker=True)))


def test_fal_provider_reports_sync_result_as_completed() -> None:
    """同步成品地址即上游任务标识，查询与取消都不得再请求上游。"""

    def handler(_: httpx.Request) -> httpx.Response:
        raise AssertionError("同步结果不应再访问上游")

    provider = FalVideoProvider(
        None,
        "fal-key",
        FAL_MINIMAX_H3_MAX_TEXT_TO_VIDEO_TEMPLATE.provider_config,
        transport=httpx.MockTransport(handler),
    )

    snapshot = asyncio.run(provider.query("https://media.example.com/result.mp4"))
    cancelled = asyncio.run(provider.cancel("https://media.example.com/result.mp4"))

    assert snapshot.status is ProviderTaskStatus.succeeded
    assert snapshot.progress == 100
    assert snapshot.result_url == "https://media.example.com/result.mp4"
    assert cancelled.status is ProviderTaskStatus.succeeded


def test_fal_provider_fetches_result_url_as_stream() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://media.example.com/result.mp4"
        return httpx.Response(200, content=b"video-bytes", headers={"content-type": "video/mp4"})

    provider = FalVideoProvider(
        None,
        "fal-key",
        FAL_MINIMAX_H3_MAX_TEXT_TO_VIDEO_TEMPLATE.provider_config,
        transport=httpx.MockTransport(handler),
    )
    chunks, content_type = asyncio.run(provider.fetch_result("https://media.example.com/result.mp4"))

    async def collect() -> bytes:
        return b"".join([chunk async for chunk in chunks])

    assert content_type == "video/mp4"
    assert asyncio.run(collect()) == b"video-bytes"


def test_fal_provider_rejects_sync_response_without_result_url() -> None:
    provider = FalVideoProvider(
        None,
        "fal-key",
        FAL_MINIMAX_H3_MAX_TEXT_TO_VIDEO_TEMPLATE.provider_config,
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"status": "COMPLETED"})),
    )

    with pytest.raises(ProviderError, match="上游未返回视频结果地址") as error:
        asyncio.run(provider.submit(make_command()))

    assert error.value.code == "invalid_response"
    assert error.value.retryable is False


def test_fal_provider_marks_http_failures_retryable() -> None:
    provider = FalVideoProvider(
        None,
        "fal-key",
        FAL_MINIMAX_H3_MAX_TEXT_TO_VIDEO_TEMPLATE.provider_config,
        transport=httpx.MockTransport(lambda _: httpx.Response(503, json={"error": {"token": "secret"}})),
    )

    with pytest.raises(ProviderError, match="上游服务暂不可用") as error:
        asyncio.run(provider.submit(make_command()))

    assert error.value.retryable is True
    assert error.value.response_body == {"error": {"token": "secret"}}


def test_fal_template_and_container_registration() -> None:
    template = FAL_MINIMAX_H3_MAX_TEXT_TO_VIDEO_TEMPLATE
    detail = get_provider_template_registry().get(template.template_id)

    assert template.provider_type == "fal"
    assert template.model_type == "video"
    assert template.input_schema["required"] == ["prompt", "prompt_expansion_mode", "resolution"]
    assert template.input_schema["properties"]["seconds"] == {"type": "integer", "minimum": 5, "maximum": 15}
    assert template.default_pricing_rules[0]["items"][0]["source_fields"] == ["seconds"]
    assert detail is not None
    assert detail["provider_type"] == "fal"
    assert "provider_config" not in detail
    assert "fal" in get_provider_registry()._builders


def test_fal_reference_template_uses_tiered_output_and_reference_material_pricing() -> None:
    template = FAL_MINIMAX_H3_MAX_REFERENCE_TO_VIDEO_TEMPLATE

    assert template.input_schema["properties"]["resolution"]["enum"] == ["480P", "768P", "1080P"]
    assert [rule["name"] for rule in template.default_pricing_rules] == ["480P", "768P", "1080P", "默认档位"]
    assert [item["unit_amount"] for item in template.default_pricing_rules[0]["items"]] == ["0.260000", "0.163200"]
    assert [item["unit_amount"] for item in template.default_pricing_rules[1]["items"]] == ["0.380000", "0.163200"]
    assert [item["unit_amount"] for item in template.default_pricing_rules[2]["items"]] == ["0.760000", "0.326400"]
    assert template.default_pricing_rules[0]["items"][1]["free_quantity"] == 4096


def test_fal_default_tier_rule_matches_requests_without_resolution() -> None:
    """兜底档位无命中条件且按 480P 计价，避免未携带 resolution 时无方案命中。"""

    fallback = FAL_MINIMAX_H3_MAX_REFERENCE_TO_VIDEO_TEMPLATE.default_pricing_rules[-1]

    assert fallback["conditions"] == []
    assert fallback["priority"] > max(
        rule["priority"] for rule in FAL_MINIMAX_H3_MAX_REFERENCE_TO_VIDEO_TEMPLATE.default_pricing_rules[:-1]
    )
    assert [item["unit_amount"] for item in fallback["items"]] == ["0.260000", "0.163200"]


def test_non_reference_fal_templates_only_charge_output_video_duration() -> None:
    for template in (
        FAL_MINIMAX_H3_MAX_TEXT_TO_VIDEO_TEMPLATE,
        FAL_MINIMAX_H3_MAX_IMAGE_TO_VIDEO_TEMPLATE,
    ):
        rules = template.default_pricing_rules
        assert [item["kind"] for item in rules[0]["items"]] == ["output_video_duration"]
        assert [item["unit_amount"] for item in rules[0]["items"]] == ["0.080000"]
        assert [item["unit_amount"] for item in rules[1]["items"]] == ["0.120000"]
        assert [item["unit_amount"] for item in rules[2]["items"]] == ["0.240000"]
        assert [item["unit_amount"] for item in rules[-1]["items"]] == ["0.080000"]


@pytest.mark.parametrize(
    ("template", "request_overrides", "expected_path", "expected_payload"),
    [
        (
            FAL_MINIMAX_H3_MAX_TEXT_TO_VIDEO_TEMPLATE,
            {},
            "/minimax/h3-max/text-to-video",
            {
                "prompt",
                "prompt_expansion_mode",
                "duration",
                "resolution",
                "aspect_ratio",
                "seed",
                "enable_safety_checker",
                "sync_mode",
            },
        ),
        (
            FAL_MINIMAX_H3_MAX_REFERENCE_TO_VIDEO_TEMPLATE,
            {"reference_image_urls": ["https://example.com/reference.jpg"]},
            "/minimax/h3-max/reference-to-video",
            {
                "prompt",
                "prompt_expansion_mode",
                "duration",
                "resolution",
                "aspect_ratio",
                "seed",
                "enable_safety_checker",
                "sync_mode",
                "reference_image_urls",
            },
        ),
        (
            FAL_MINIMAX_H3_MAX_IMAGE_TO_VIDEO_TEMPLATE,
            {"image_url": "https://example.com/start.jpg", "end_image_url": "https://example.com/end.jpg"},
            "/minimax/h3-max/image-to-video",
            {
                "prompt",
                "prompt_expansion_mode",
                "duration",
                "resolution",
                "aspect_ratio",
                "seed",
                "enable_safety_checker",
                "sync_mode",
                "image_url",
                "end_image_url",
            },
        ),
    ],
)
def test_fal_templates_fix_endpoint_and_project_only_declared_fields(
    template, request_overrides, expected_path: str, expected_payload: set[str]
) -> None:
    def handler(http_request: httpx.Request) -> httpx.Response:
        assert http_request.url.path == expected_path
        payload = json.loads(http_request.content)
        assert set(payload) == expected_payload
        assert "model" not in payload
        assert "unexpected" not in payload
        assert payload["duration"] == 5
        return httpx.Response(200, json={"video": {"url": "https://media.example.com/result.mp4"}})

    provider = FalVideoProvider(
        None,
        "fal-key",
        template.provider_config,
        transport=httpx.MockTransport(handler),
    )

    asyncio.run(provider.submit(make_command(unexpected="discarded", **request_overrides)))
