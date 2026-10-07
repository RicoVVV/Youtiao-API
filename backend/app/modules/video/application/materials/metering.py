"""视频输入素材的可信计量与受控存储。

本模块把已归一化的素材来源（远程 URL 或受控存储文件）解析为可计价的稳定事实：素材类别、内容
摘要、字节大小与实测时长，并提供受控存储路径解析与过期清理。远程获取强制 SSRF 校验与资源上限，
素材类别一律由内容嗅探与媒体解析判定，不采信客户端声明的 MIME 或文件后缀。所有失败以
``ValueError`` 上报，由调用方决定响应，不在本模块写入数据库或调用 Provider。
"""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import json
import os
import re
import socket
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import ROUND_CEILING, Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

import aiohttp
from aiohttp.abc import AbstractResolver

from app.core.config import get_settings
from app.core.errors import ValidationError

_READ_CHUNK_BYTES = 1024 * 1024
_SNIFF_BYTES = 64
_IMAGE_HEADER_BYTES = 262144
_RESOURCE_ID_PATTERN = re.compile(r"^[0-9a-f]{32}(\.[a-z0-9]{1,8})?$")
_SUFFIX_PATTERN = re.compile(r"^\.[a-z0-9]{1,8}$")
_ALLOWED_SCHEMES = {"http", "https"}
_INCOMING_DIRECTORY = "_incoming"
_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
_AMOUNT_PRECISION = Decimal("0.000001")
_VIDEO_CATEGORY = "video"
_IMAGE_CATEGORY = "image"
_AUDIO_CATEGORY = "audio"
_SUPPORTED_CATEGORIES = frozenset({_VIDEO_CATEGORY, _IMAGE_CATEGORY, _AUDIO_CATEGORY})
_IMAGE_FORMATS = {
    b"\xff\xd8\xff": "jpeg",
    b"\x89PNG\r\n\x1a\n": "png",
    b"GIF87a": "gif",
    b"GIF89a": "gif",
    b"BM": "bmp",
    b"II*\x00": "tiff",
    b"MM\x00*": "tiff",
}


@dataclass(frozen=True)
class MaterialProbe:
    """单个素材经嗅探与媒体解析后的可信计量结果。"""

    category: str
    content_sha256: str
    size_bytes: int
    duration_seconds: Decimal | None = None
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class _ValidatedTarget:
    url: str
    host: str
    port: int
    addresses: tuple[str, ...]


class _ValidatedAddressResolver(AbstractResolver):
    def __init__(self, target: _ValidatedTarget) -> None:
        self._target = target

    async def resolve(self, host: str, port: int = 0, family: int = socket.AF_UNSPEC) -> list[dict[str, Any]]:
        if host != self._target.host or port != self._target.port:
            raise OSError("unexpected connection target")
        return [
            {
                "hostname": self._target.host,
                "host": address,
                "port": self._target.port,
                "family": socket.AF_INET6 if ":" in address else socket.AF_INET,
                "proto": 0,
                "flags": 0,
            }
            for address in self._target.addresses
        ]

    async def close(self) -> None:
        return None


class _MaterialResponse:
    def __init__(self, session: aiohttp.ClientSession, response: aiohttp.ClientResponse) -> None:
        self._session = session
        self._response = response

    @property
    def status_code(self) -> int:
        return self._response.status

    @property
    def headers(self):
        return self._response.headers

    async def aiter_bytes(self, chunk_size: int):
        async for chunk in self._response.content.iter_chunked(chunk_size):
            yield chunk

    async def aclose(self) -> None:
        self._response.release()
        await self._session.close()


def material_storage_root() -> Path:
    """返回受控临时素材的存储根目录。"""

    return get_settings().video_material_storage_dir


def normalize_suffix(filename: str | None) -> str:
    """从客户端文件名提取受控后缀，无法识别时返回空串。"""

    if not isinstance(filename, str):
        return ""
    candidate = Path(filename).suffix.lower()
    return candidate if _SUFFIX_PATTERN.fullmatch(candidate) else ""


def new_resource_id(suffix: str) -> str:
    """生成新的受控存储资源标识，不包含客户端可控内容。"""

    return f"{uuid4().hex}{suffix}"


def safe_material_path(resource_id: str) -> Path:
    """把资源标识解析为存储根目录下的安全路径，拒绝越权或非法标识。"""

    if not isinstance(resource_id, str) or not _RESOURCE_ID_PATTERN.fullmatch(resource_id):
        raise ValueError("素材资源标识不合法")
    root = material_storage_root().resolve()
    path = (root / resource_id).resolve()
    if root not in path.parents or path == root:
        raise ValueError("素材资源标识不合法")
    return path


def incoming_material_path(resource_id: str) -> Path:
    """返回下载或写入过程的临时落盘路径，该目录不对外提供读取。"""

    root = material_storage_root().resolve()
    return root / _INCOMING_DIRECTORY / f"{resource_id}.part"


def resolve_material_public_url(resource_id: str, *, public_base_url: str) -> str:
    """生成 Provider 可下载的受控素材公开地址。"""

    return f"{public_base_url.rstrip('/')}/v1/videos/materials/{resource_id}"


async def probe_stored_file(
    path: Path,
    *,
    allowed_categories: Iterable[str],
    suffix: str = "",
) -> MaterialProbe:
    """嗅探并解析受控存储中的素材文件，返回可信计量结果。"""

    category, extras = await _detect_category(path, suffix=suffix)
    _ensure_allowed(category, allowed_categories)
    size_bytes = path.stat().st_size
    content_sha256 = await asyncio.to_thread(_sha256_file, path)
    duration: Decimal | None = None
    if category in {_VIDEO_CATEGORY, _AUDIO_CATEGORY}:
        duration = _probe_duration(extras)
    return MaterialProbe(
        category=category,
        content_sha256=content_sha256,
        size_bytes=size_bytes,
        duration_seconds=duration,
        extras=extras,
    )


async def probe_remote_url(url: str, *, allowed_categories: Iterable[str], suffix: str = "") -> MaterialProbe:
    """安全下载远程素材并完成嗅探与媒体解析，结束后立即删除临时文件。"""

    temporary = await download_remote_material(url)
    try:
        return await probe_stored_file(temporary, allowed_categories=allowed_categories, suffix=suffix)
    finally:
        temporary.unlink(missing_ok=True)


async def download_remote_material(url: str) -> Path:
    """按 SSRF 约束下载远程素材到临时目录，返回临时文件路径。

    仅允许受控协议，逐跳校验目标地址并限制重定向次数、超时与响应大小；调用方负责删除返回的临时文件。
    """

    settings = get_settings()
    current = url
    for _ in range(settings.video_material_max_redirects + 1):
        target = await _validate_public_target(current)
        response = await _open_material_response(target)
        if response.status_code in _REDIRECT_STATUSES:
            location = response.headers.get("location")
            await response.aclose()
            if not location:
                raise ValueError("输入素材下载重定向缺少目标地址")
            current = _absolute_redirect(current, location)
            continue
        if response.status_code >= 400:
            await response.aclose()
            raise ValueError("输入素材下载失败")
        return await _stream_response_to_file(response)
    raise ValueError("输入素材下载重定向次数超出限制")


async def cleanup_expired_materials(*, now: datetime | None = None) -> int:
    """删除超过保留期限的受控素材文件，返回删除数量。"""

    settings = get_settings()
    deadline = (now or datetime.now(UTC)) - timedelta(hours=settings.video_material_retention_hours)
    root = material_storage_root()
    removed = 0
    for directory in (root, root / _INCOMING_DIRECTORY):
        if not directory.is_dir():
            continue
        for entry in directory.iterdir():
            if not entry.is_file():
                continue
            try:
                modified = datetime.fromtimestamp(entry.stat().st_mtime, tz=UTC)
            except OSError:
                continue
            if modified <= deadline:
                entry.unlink(missing_ok=True)
                removed += 1
    return removed


async def _open_material_response(target: _ValidatedTarget) -> _MaterialResponse:
    settings = get_settings()
    timeout = settings.video_material_download_timeout_seconds
    try:
        client_session = aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(resolver=_ValidatedAddressResolver(target)),
            timeout=aiohttp.ClientTimeout(total=None, connect=timeout, sock_read=timeout),
            trust_env=False,
        )
        response = await client_session.get(target.url, allow_redirects=False)
        return _MaterialResponse(client_session, response)
    except Exception as exc:  # noqa: BLE001 - 归并为统一的拒绝原因，避免泄露底层网络细节
        if "client_session" in locals():
            await client_session.close()
        raise ValueError("输入素材下载失败") from exc


async def _stream_response_to_file(response) -> Path:
    settings = get_settings()
    content_length = response.headers.get("content-length")
    if content_length is not None:
        try:
            declared_size = int(content_length)
        except ValueError:
            declared_size = 0
        if declared_size > settings.video_material_max_bytes:
            await response.aclose()
            raise ValueError("输入素材超出大小限制")
    temporary = incoming_material_path(uuid4().hex)
    temporary.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    try:
        with temporary.open("wb") as output:
            async for chunk in response.aiter_bytes(_READ_CHUNK_BYTES):
                total += len(chunk)
                if total > settings.video_material_max_bytes:
                    raise ValueError("输入素材超出大小限制")
                output.write(chunk)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    finally:
        await response.aclose()
    if total == 0:
        temporary.unlink(missing_ok=True)
        raise ValueError("输入素材为空")
    return temporary


def _absolute_redirect(current: str, location: str) -> str:
    from urllib.parse import urljoin

    resolved = urljoin(current, location.strip())
    return resolved


async def _validate_public_target(url: str) -> _ValidatedTarget:
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise ValueError("输入素材地址协议不受支持")
    if parsed.username or parsed.password:
        raise ValueError("输入素材地址不合法")
    host = parsed.hostname
    if not host:
        raise ValueError("输入素材地址不合法")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    addresses = await _resolve_addresses(host, port)
    if not addresses:
        raise ValueError("输入素材地址无法解析")
    for address in addresses:
        try:
            parsed_ip = ipaddress.ip_address(address)
        except ValueError as exc:
            raise ValueError("输入素材地址不合法") from exc
        if not parsed_ip.is_global:
            raise ValueError("输入素材地址不被允许")
    return _ValidatedTarget(url=url, host=host, port=port, addresses=tuple(addresses))


async def _resolve_addresses(host: str, port: int) -> list[str]:
    try:
        parsed_ip = ipaddress.ip_address(host)
    except ValueError:
        parsed_ip = None
    if parsed_ip is not None:
        return [str(parsed_ip)]
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ValueError("输入素材地址无法解析") from exc
    return [info[4][0] for info in infos]


async def _detect_category(path: Path, *, suffix: str) -> tuple[str, dict[str, Any]]:
    header = await asyncio.to_thread(_read_prefix, path, _IMAGE_HEADER_BYTES)
    if not header:
        raise ValueError("输入素材为空")
    sniffed = _sniff_container(header[:_SNIFF_BYTES])
    if sniffed is None:
        raise ValueError("无法识别输入素材的媒体格式")
    if sniffed == _IMAGE_CATEGORY:
        return _IMAGE_CATEGORY, _image_dimensions(header)
    return await _probe_media_streams(path, declared=suffix, sniffed=sniffed)


async def _probe_media_streams(path: Path, *, declared: str, sniffed: str) -> tuple[str, dict[str, Any]]:
    data = await _run_ffprobe(path)
    streams = [stream for stream in data.get("streams", []) if isinstance(stream, dict)]
    has_video = any(stream.get("codec_type") == "video" for stream in streams)
    has_audio = any(stream.get("codec_type") == "audio" for stream in streams)
    if has_video:
        category = _VIDEO_CATEGORY
    elif has_audio:
        category = _AUDIO_CATEGORY
    else:
        raise ValueError("无法识别输入素材的媒体格式")
    container = data.get("format", {}).get("format_name")
    extras: dict[str, Any] = {
        "container": container if isinstance(container, str) else None,
        "video_streams": sum(1 for stream in streams if stream.get("codec_type") == "video"),
        "audio_streams": sum(1 for stream in streams if stream.get("codec_type") == "audio"),
        "sniffed": sniffed,
        "declared_suffix": declared or None,
        "duration": _format_duration(data),
    }
    return category, extras


def _probe_duration(extras: dict[str, Any]) -> Decimal:
    settings = get_settings()
    raw = extras.get("duration")
    try:
        duration = Decimal(str(raw))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("输入素材时长无法确定") from exc
    if not duration.is_finite() or duration <= 0:
        raise ValueError("输入素材时长无法确定")
    if duration > settings.video_material_max_video_seconds:
        raise ValueError("输入视频时长超出限制")
    return duration.quantize(_AMOUNT_PRECISION, rounding=ROUND_CEILING)


def _format_duration(data: dict[str, Any]) -> str | None:
    container = data.get("format")
    if isinstance(container, dict):
        duration = container.get("duration")
        if isinstance(duration, str):
            return duration
    for stream in data.get("streams", []):
        if isinstance(stream, dict) and isinstance(stream.get("duration"), str):
            return stream["duration"]
    return None


async def _run_ffprobe(path: Path) -> dict[str, Any]:
    settings = get_settings()
    try:
        process = await asyncio.create_subprocess_exec(
            "ffprobe",
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except (FileNotFoundError, NotImplementedError) as exc:
        raise ValueError("服务端缺少媒体探测能力") from exc
    try:
        stdout, _ = await asyncio.wait_for(
            process.communicate(), timeout=settings.video_material_download_timeout_seconds
        )
    except TimeoutError as exc:
        process.kill()
        await process.wait()
        raise ValueError("输入素材媒体解析超时") from exc
    if process.returncode != 0:
        raise ValueError("输入素材媒体解析失败")
    try:
        parsed = json.loads(stdout.decode("utf-8", "replace") or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError("输入素材媒体解析失败") from exc
    if not isinstance(parsed, dict):
        raise ValueError("输入素材媒体解析失败")
    return parsed


def _sniff_container(header: bytes) -> str | None:
    if any(header.startswith(magic) for magic in _IMAGE_FORMATS):
        return _IMAGE_CATEGORY
    if header[:4] == b"RIFF":
        form = header[8:12]
        if form == b"WEBP":
            return _IMAGE_CATEGORY
        if form == b"AVI ":
            return _VIDEO_CATEGORY
        if form == b"WAVE":
            return _AUDIO_CATEGORY
    if header[4:8] == b"ftyp":
        return _VIDEO_CATEGORY
    if header[:4] == b"\x1aE\xdf\xa3":
        return _VIDEO_CATEGORY
    if header[:3] == b"ID3" or header[:2] in {b"\xff\xfb", b"\xff\xf3", b"\xff\xf2", b"\xff\xf1"}:
        return _AUDIO_CATEGORY
    if header[:4] == b"OggS" or header[:4] == b"fLaC":
        return _AUDIO_CATEGORY
    return None


def _image_dimensions(header: bytes) -> dict[str, Any]:
    settings = get_settings()
    dimensions = _parse_image_dimensions(header)
    if dimensions is None:
        return {"width": None, "height": None}
    width, height = dimensions
    if width <= 0 or height <= 0 or width * height > settings.video_material_max_image_pixels:
        raise ValueError("输入图片像素超出限制")
    return {"width": width, "height": height}


def _parse_image_dimensions(header: bytes) -> tuple[int, int] | None:
    if header.startswith(b"\x89PNG\r\n\x1a\n") and len(header) >= 24:
        return int.from_bytes(header[16:20], "big"), int.from_bytes(header[20:24], "big")
    if header[:6] in {b"GIF87a", b"GIF89a"} and len(header) >= 10:
        return int.from_bytes(header[6:8], "little"), int.from_bytes(header[8:10], "little")
    if header.startswith(b"BM") and len(header) >= 26:
        return int.from_bytes(header[18:22], "little"), int.from_bytes(header[22:26], "little")
    if header.startswith(b"\xff\xd8\xff"):
        return _jpeg_dimensions(header)
    if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return _webp_dimensions(header)
    return None


def _jpeg_dimensions(header: bytes) -> tuple[int, int] | None:
    index = 2
    while index + 9 < len(header):
        if header[index] != 0xFF:
            index += 1
            continue
        marker = header[index + 1]
        if marker in {0xD8, 0xD9} or 0xD0 <= marker <= 0xD7:
            index += 2
            continue
        segment_length = int.from_bytes(header[index + 2 : index + 4], "big")
        if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
            height = int.from_bytes(header[index + 5 : index + 7], "big")
            width = int.from_bytes(header[index + 7 : index + 9], "big")
            return width, height
        if segment_length <= 0:
            return None
        index += 2 + segment_length
    return None


def _webp_dimensions(header: bytes) -> tuple[int, int] | None:
    if len(header) < 30:
        return None
    chunk = header[12:16]
    if chunk == b"VP8X":
        width = int.from_bytes(header[24:27], "little") + 1
        height = int.from_bytes(header[27:30], "little") + 1
        return width, height
    if chunk == b"VP8L" and len(header) >= 25:
        bits = int.from_bytes(header[21:25], "little")
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    if chunk == b"VP8 " and len(header) >= 30:
        width = int.from_bytes(header[26:28], "little") & 0x3FFF
        height = int.from_bytes(header[28:30], "little") & 0x3FFF
        return width, height
    return None


def _ensure_allowed(category: str, allowed_categories: Iterable[str]) -> None:
    if category not in _SUPPORTED_CATEGORIES:
        raise ValueError("无法识别输入素材的媒体格式")
    allowed = {item for item in allowed_categories if isinstance(item, str)}
    if allowed and category not in allowed:
        raise ValidationError(
            f"输入素材类别不受支持：{category}",
            code="video.material_category_unsupported",
            params={"category": category},
        )


def _read_prefix(path: Path, size: int) -> bytes:
    with path.open("rb") as stream:
        return stream.read(size)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(_READ_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def replace_stored_material(temporary: Path, resource_id: str) -> Path:
    """把写满的临时文件原子移动到受控资源路径，避免暴露半成品。"""

    target = safe_material_path(resource_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    os.replace(temporary, target)
    return target
