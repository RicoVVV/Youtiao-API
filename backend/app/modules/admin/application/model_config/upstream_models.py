"""管理员渠道上游可用模型拉取服务。

只负责按渠道连接信息请求上游模型列表接口并归一化模型名，不写入数据库；
认证信息不写入日志或响应。
"""

import logging
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.errors import NotFoundError, UpstreamUnavailableError, ValidationError
from app.infrastructure.http.client import get_async_http_client
from app.modules.admin.crud.channel_crud import ChannelCrud

logger = logging.getLogger(__name__)

_MODELS_SUFFIX = "/models"
_REQUEST_TIMEOUT_SECONDS = 15.0
"""模型列表接口的交互式请求超时：管理台按钮等待时间必须明显短于生成请求。"""


class UpstreamModelApplicationService:
    """按渠道地址与密钥拉取上游可用模型名。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def fetch_models(
        self,
        *,
        base_url: str | None,
        api_key: str | None,
        channel_id: UUID | None,
        header_override: dict[str, Any],
    ) -> dict[str, object]:
        """请求上游模型列表并返回去重排序后的模型名。

        参数：``base_url`` 与 ``api_key`` 为表单中填写的渠道连接信息；仅传 ``channel_id`` 时复用已保存的
        地址、密钥与渠道请求头，便于编辑已有渠道时直接拉取。
        异常：渠道不存在返回 404；缺少地址或密钥、上游拒绝认证或返回非法结构返回 422；
        网络不可达返回 503。
        """

        url, key, headers, tls_max_version = await self._resolve_connection(
            base_url=base_url,
            api_key=api_key,
            channel_id=channel_id,
            header_override=header_override,
        )
        request_headers = {"Accept": "application/json", **_string_headers(headers)}
        if key and not any(name.lower() == "authorization" for name in request_headers):
            # 渠道显式配置的认证头优先，默认按 OpenAI 兼容约定使用 Bearer。
            request_headers["Authorization"] = f"Bearer {key}"
        client = get_async_http_client(tls_max_version=tls_max_version)
        try:
            response = await client.get(_models_url(url), headers=request_headers, timeout=_REQUEST_TIMEOUT_SECONDS)
        except httpx.HTTPError as exc:
            logger.warning("上游模型列表请求失败 host=%s: %s", _host(url), type(exc).__name__)
            raise UpstreamUnavailableError("无法连接上游模型列表接口") from exc
        if response.status_code in (401, 403):
            raise ValidationError("上游鉴权失败，请检查渠道 API Key")
        if response.status_code >= 400:
            raise ValidationError(f"上游模型列表接口返回 HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise ValidationError("上游模型列表返回的不是合法 JSON") from exc
        models = _extract_model_ids(payload)
        if not models:
            raise ValidationError("上游未返回任何可用模型")
        return {"models": models}

    async def _resolve_connection(
        self,
        *,
        base_url: str | None,
        api_key: str | None,
        channel_id: UUID | None,
        header_override: dict[str, Any],
    ) -> tuple[str, str, dict[str, Any], str | None]:
        """合并表单与已保存渠道的连接信息，缺项时抛出校验异常。"""

        channel = None
        if channel_id is not None:
            async with self._session_factory() as session:
                channel = await session.run_sync(lambda sync_session: ChannelCrud(sync_session).get(channel_id))
            if channel is None:
                raise NotFoundError("渠道不存在")
        url = (base_url or (channel.base_url if channel else "")).strip()
        key = (api_key or (channel.api_key if channel else "")).strip()
        headers = dict(channel.header_override) if channel is not None else {}
        headers.update(header_override)
        if not url:
            raise ValidationError("请填写渠道 URL")
        if not url.startswith(("http://", "https://")):
            raise ValidationError("渠道 URL 必须使用 HTTP 或 HTTPS 协议")
        if not key:
            raise ValidationError("请填写渠道 API Key")
        tls_max_version = channel.config.get("tls_max_version") if channel is not None else None
        return url, key, headers, tls_max_version if isinstance(tls_max_version, str) else None


def _models_url(base_url: str) -> str:
    """把渠道地址补全为上游模型列表地址。

    已显式指向 ``/models`` 时直接使用；地址已带版本段（``/v1``、``/v1beta``、``/api/v3``）时只在末尾
    追加 ``/models``；其余情况按 OpenAI 兼容约定补上 ``/v1/models``。
    """

    url = base_url.strip().rstrip("/")
    if url.endswith(_MODELS_SUFFIX):
        return url
    if url.endswith(("/v1", "/v1beta", "/api/v3")):
        return f"{url}{_MODELS_SUFFIX}"
    return f"{url}/v1{_MODELS_SUFFIX}"


def _string_headers(headers: dict[str, Any]) -> dict[str, str]:
    """把渠道请求头归一化为字符串键值，忽略空值与非法结构。"""

    return {
        str(key): str(value)
        for key, value in headers.items()
        if isinstance(key, str) and isinstance(value, str | int | float | bool)
    }


def _extract_model_ids(payload: Any) -> list[str]:
    """兼容 OpenAI、Anthropic 与 Gemini 的模型列表结构，提取去重排序后的模型名。"""

    candidates: list[Any] = []
    if isinstance(payload, dict):
        for key in ("data", "models"):
            value = payload.get(key)
            if isinstance(value, list):
                candidates.extend(value)
    elif isinstance(payload, list):
        candidates.extend(payload)
    names: set[str] = set()
    for item in candidates:
        name = _model_name(item)
        if name:
            names.add(name)
    return sorted(names)


def _model_name(item: Any) -> str | None:
    """从单个列表元素中取出模型名，兼容字符串、``id``、``model`` 与 Gemini 的 ``name``。"""

    raw: Any = item
    if isinstance(item, dict):
        raw = next((item[key] for key in ("id", "model", "name") if isinstance(item.get(key), str)), None)
    if not isinstance(raw, str):
        return None
    # Gemini 返回 "models/gemini-2.5-pro"，对平台来说模型名不需要资源前缀。
    name = raw.removeprefix("models/").strip()
    return name or None


def _host(url: str) -> str:
    """只保留主机名用于日志，避免把查询参数写入日志。"""

    return httpx.URL(url).host
