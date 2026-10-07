"""提供进程内复用的 HTTP 客户端、受限连接池与显式释放入口。

本模块不保存渠道地址、认证信息或业务错误语义；调用方负责处理请求及响应，
并且不得关闭通过本模块取得的共享客户端。
"""

import ssl
from functools import lru_cache

import httpx

from app.core.config import get_settings

KEEPALIVE_EXPIRY_SECONDS = 30.0
CONNECT_TIMEOUT_SECONDS = 120.0
WRITE_TIMEOUT_SECONDS = 30.0
POOL_TIMEOUT_SECONDS = 120.0

_TLS_MAX_VERSIONS = {"1.2": ssl.TLSVersion.TLSv1_2, "1.3": ssl.TLSVersion.TLSv1_3}
"""渠道可收敛的最高 TLS 版本。

部分上游链路上的中间设备会直接丢弃声明了 TLS1.3 的 ClientHello，此时按渠道显式降级到 1.2 才能建连；
仅提供 1.2 与 1.3，避免配置出低于安全下限的组合。
"""


def _create_http_client(transport: httpx.BaseTransport | None = None) -> httpx.Client:
    """创建具备固定资源上限的同步 HTTP 客户端。

    参数:
        transport: 可选的底层传输实现，仅供测试注入 MockTransport 以隔离真实网络。

    返回:
        配置好连接池和阶段性超时的 HTTP 客户端。
    """

    settings = get_settings()
    return httpx.Client(
        limits=httpx.Limits(
            max_connections=settings.http_max_connections,
            max_keepalive_connections=settings.http_max_keepalive_connections,
            keepalive_expiry=KEEPALIVE_EXPIRY_SECONDS,
        ),
        timeout=httpx.Timeout(
            connect=CONNECT_TIMEOUT_SECONDS,
            read=settings.provider_read_timeout_seconds,
            write=WRITE_TIMEOUT_SECONDS,
            pool=POOL_TIMEOUT_SECONDS,
        ),
        transport=transport,
    )


def _tls_verification(tls_max_version: str | None) -> ssl.SSLContext | bool:
    """把渠道要求的最高 TLS 版本转换为证书校验参数。

    参数:
        tls_max_version: 渠道配置的最高 TLS 版本，取值 ``"1.2"`` 或 ``"1.3"``；未配置时传 ``None``。

    返回:
        配置了 ``maximum_version`` 的证书校验上下文；未配置时返回 ``True`` 以沿用 httpx 默认校验。

    异常:
        取值不在支持范围内时抛出 ``ValueError``，避免静默回落到不受控的协议版本。
    """

    if tls_max_version is None:
        return True
    if tls_max_version not in _TLS_MAX_VERSIONS:
        raise ValueError("渠道配置的最高 TLS 版本只支持 1.2 或 1.3")
    context = ssl.create_default_context()
    context.maximum_version = _TLS_MAX_VERSIONS[tls_max_version]
    return context


def _create_async_http_client(
    transport: httpx.AsyncBaseTransport | None = None, tls_max_version: str | None = None
) -> httpx.AsyncClient:
    """创建具备固定资源上限的异步 HTTP 客户端。"""

    settings = get_settings()
    return httpx.AsyncClient(
        limits=httpx.Limits(
            max_connections=settings.http_max_connections,
            max_keepalive_connections=settings.http_max_keepalive_connections,
            keepalive_expiry=KEEPALIVE_EXPIRY_SECONDS,
        ),
        timeout=httpx.Timeout(
            connect=CONNECT_TIMEOUT_SECONDS,
            read=settings.provider_read_timeout_seconds,
            write=WRITE_TIMEOUT_SECONDS,
            pool=POOL_TIMEOUT_SECONDS,
        ),
        verify=_tls_verification(tls_max_version),
        transport=transport,
    )


@lru_cache(maxsize=1)
def _get_cached_http_client() -> httpx.Client:
    """惰性创建当前进程唯一的默认客户端，供公开工厂复用。"""

    return _create_http_client()


def get_http_client(transport: httpx.BaseTransport | None = None) -> httpx.Client:
    """获取 HTTP 客户端。

    参数:
        transport: 测试时可传入的隔离传输；传入时返回独立实例，不写入进程共享缓存。

    返回:
        未传入传输时返回当前进程共享客户端，否则返回使用指定传输的独立客户端。

    副作用:
        首次无传输调用会创建并缓存连接池，调用方不得自行关闭该共享实例。
    """

    if transport is not None:
        return _create_http_client(transport=transport)
    return _get_cached_http_client()


_cached_async_clients: dict[str | None, httpx.AsyncClient] = {}
"""当前进程共享的异步客户端，按渠道要求的最高 TLS 版本区分，未配置版本时以 ``None`` 为键。"""


def get_async_http_client(
    transport: httpx.AsyncBaseTransport | None = None, tls_max_version: str | None = None
) -> httpx.AsyncClient:
    """获取异步 HTTP 客户端。

    参数:
        transport: 测试时可传入的隔离传输；传入时返回独立实例，不写入进程共享缓存。
        tls_max_version: 渠道要求的最高 TLS 版本，取值 ``"1.2"`` 或 ``"1.3"``；未配置时传 ``None``。

    返回:
        未传入传输时返回当前进程共享客户端，同一 TLS 版本复用同一实例；否则返回独立客户端。

    副作用:
        首次使用某个 TLS 版本会创建并缓存该版本的连接池，调用方不得自行关闭共享实例。
    """

    if transport is not None:
        return _create_async_http_client(transport=transport, tls_max_version=tls_max_version)
    client = _cached_async_clients.get(tls_max_version)
    if client is None:
        client = _create_async_http_client(tls_max_version=tls_max_version)
        _cached_async_clients[tls_max_version] = client
    return client


def close_http_client() -> None:
    """关闭已缓存的共享客户端并清除缓存，使后续调用能创建新的连接池。

    该函数可重复调用；尚未创建共享客户端时不会创建客户端，也不会抛出异常。
    """

    cached_client = _get_cached_http_client.cache_info().currsize
    if cached_client:
        # 仅在实例存在时读取缓存，避免关闭入口意外初始化连接池。
        _get_cached_http_client().close()
    _get_cached_http_client.cache_clear()


async def close_async_http_client() -> None:
    """关闭全部已缓存的共享异步客户端（含各 TLS 版本变体）并清除缓存。"""

    for client in _cached_async_clients.values():
        await client.aclose()
    _cached_async_clients.clear()
