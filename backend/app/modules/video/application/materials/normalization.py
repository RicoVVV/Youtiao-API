from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from starlette.datastructures import UploadFile

from app.core.config import get_settings
from app.core.errors import ValidationError
from app.modules.pricing.application.engine import MaterialFacts
from app.modules.video.application.materials.metering import (
    MaterialProbe,
    download_remote_material,
    incoming_material_path,
    new_resource_id,
    normalize_suffix,
    probe_remote_url,
    probe_stored_file,
    replace_stored_material,
    resolve_material_public_url,
)


@dataclass(frozen=True)
class NormalizedInputMaterial:
    field_name: str
    position: int
    category: str
    resource_id: str
    content_sha256: str
    size_bytes: int
    duration_seconds: Decimal | None
    extras: dict[str, Any]


@dataclass(frozen=True)
class NormalizedMaterialRequest:
    request: dict[str, Any]
    facts: MaterialFacts
    materials: tuple[NormalizedInputMaterial, ...]


async def normalize_video_materials(
    request: dict[str, Any],
    *,
    material_fields: dict[str, Any],
    uploaded_files: dict[str, list[UploadFile]],
    public_base_url: str,
) -> NormalizedMaterialRequest:
    normalized_request = dict(request)
    unsupported_upload_fields = set(uploaded_files) - set(material_fields)
    if unsupported_upload_fields:
        raise ValidationError(
            f"请求包含模型不支持的上传素材字段：{sorted(unsupported_upload_fields)[0]}",
            code="contract.unsupported_upload_fields",
            params={"name": sorted(unsupported_upload_fields)[0]},
        )
    image_counts: dict[str, int] = defaultdict(int)
    video_seconds: dict[str, Decimal] = defaultdict(Decimal)
    audio_seconds: dict[str, Decimal] = defaultdict(Decimal)
    image_tokens: dict[str, Decimal] = defaultdict(Decimal)
    image_dimensions: dict[str, list[tuple[int, int]]] = defaultdict(list)
    material_snapshot: list[dict[str, object]] = []
    materials: list[NormalizedInputMaterial] = []
    for field_name, declaration in material_fields.items():
        if not isinstance(field_name, str) or not isinstance(declaration, dict):
            raise ValueError("视频模型素材契约不合法")
        allowed_categories = declaration.get("categories")
        multiple = declaration.get("multiple")
        if not isinstance(allowed_categories, list) or not all(isinstance(item, str) for item in allowed_categories):
            raise ValueError("视频模型素材契约不合法")
        if not isinstance(multiple, bool):
            raise ValueError("视频模型素材契约不合法")
        values = _string_values(request.get(field_name), field_name=field_name, multiple=multiple)
        files = uploaded_files.get(field_name, [])
        if not multiple and len(values) + len(files) > 1:
            raise ValidationError(
                f"字段 {field_name} 仅支持一个素材",
                code="contract.field_single_material_only",
                params={"name": field_name},
            )
        resolved_values: list[str] = []
        for position, value in enumerate(values):
            if _supports_public_image_urls(allowed_categories):
                _validate_public_image_url(value)
                probe = await probe_remote_url(value, allowed_categories=allowed_categories)
                _record_probe_facts(
                    field_name,
                    probe,
                    image_counts=image_counts,
                    image_dimensions=image_dimensions,
                    image_tokens=image_tokens,
                    video_seconds=video_seconds,
                    audio_seconds=audio_seconds,
                )
                material_snapshot.append(_public_material_snapshot(field_name, position, probe))
                resolved_values.append(value)
                continue
            material = await _store_remote_material(
                value,
                field_name=field_name,
                position=position,
                allowed_categories=allowed_categories,
            )
            materials.append(material)
            resolved_values.append(resolve_material_public_url(material.resource_id, public_base_url=public_base_url))
        for file in files:
            position = len(resolved_values)
            material = await _store_uploaded_material(
                file,
                field_name=field_name,
                position=position,
                allowed_categories=allowed_categories,
            )
            materials.append(material)
            resolved_values.append(resolve_material_public_url(material.resource_id, public_base_url=public_base_url))
        if resolved_values:
            normalized_request[field_name] = resolved_values if multiple else resolved_values[0]
        for material in materials:
            if material.field_name != field_name:
                continue
            if material.category == "image":
                image_counts[field_name] += 1
                width = material.extras.get("width")
                height = material.extras.get("height")
                if isinstance(width, int) and isinstance(height, int):
                    image_dimensions[field_name].append((width, height))
                    image_tokens[field_name] += Decimal(width * height) / Decimal(1024)
            elif material.category == "video" and material.duration_seconds is not None:
                video_seconds[field_name] += material.duration_seconds
            elif material.category == "audio" and material.duration_seconds is not None:
                audio_seconds[field_name] += material.duration_seconds
    facts = MaterialFacts(
        image_counts=dict(image_counts),
        video_seconds=dict(video_seconds),
        image_dimensions={field: tuple(values) for field, values in image_dimensions.items()},
        audio_seconds=dict(audio_seconds),
        image_tokens=dict(image_tokens),
        snapshot=tuple(material_snapshot) + tuple(_material_snapshot(material) for material in materials),
    )
    return NormalizedMaterialRequest(request=normalized_request, facts=facts, materials=tuple(materials))


def _supports_public_image_urls(allowed_categories: list[str]) -> bool:
    return allowed_categories == ["image"]


def _validate_public_image_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password or not parsed.hostname:
        raise ValueError("输入图片地址不合法")


def _string_values(value: Any, *, field_name: str, multiple: bool) -> list[str]:
    if value is None:
        return []
    if multiple:
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                value = [value]
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ValidationError(
                f"字段 {field_name} 类型必须为 array",
                code="contract.field_type_mismatch",
                params={"name": field_name, "expected": "array"},
            )
        return value
    if not isinstance(value, str):
        raise ValidationError(
            f"字段 {field_name} 类型必须为 string",
            code="contract.field_type_mismatch",
            params={"name": field_name, "expected": "string"},
        )
    return [value]


async def _store_remote_material(
    url: str,
    *,
    field_name: str,
    position: int,
    allowed_categories: list[str],
) -> NormalizedInputMaterial:
    suffix = normalize_suffix(urlparse(url).path)
    temporary = await download_remote_material(url)
    try:
        return await _probe_and_store(
            temporary,
            suffix=suffix,
            field_name=field_name,
            position=position,
            allowed_categories=allowed_categories,
        )
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


async def _store_uploaded_material(
    upload: UploadFile,
    *,
    field_name: str,
    position: int,
    allowed_categories: list[str],
) -> NormalizedInputMaterial:
    suffix = normalize_suffix(upload.filename)
    temporary = incoming_material_path(new_resource_id(suffix))
    try:
        await _write_uploaded_file(upload, temporary)
        return await _probe_and_store(
            temporary,
            suffix=suffix,
            field_name=field_name,
            position=position,
            allowed_categories=allowed_categories,
        )
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()


async def _write_uploaded_file(upload: UploadFile, temporary: Path) -> None:
    limit = get_settings().video_material_max_bytes
    temporary.parent.mkdir(parents=True, exist_ok=True)
    size = 0
    with temporary.open("wb") as output:
        while chunk := await upload.read(1024 * 1024):
            size += len(chunk)
            if size > limit:
                raise ValueError("输入素材超出大小限制")
            output.write(chunk)
    if size == 0:
        raise ValueError("输入素材为空")


async def _probe_and_store(
    temporary: Path,
    *,
    suffix: str,
    field_name: str,
    position: int,
    allowed_categories: list[str],
) -> NormalizedInputMaterial:
    probe = await probe_stored_file(temporary, allowed_categories=allowed_categories, suffix=suffix)
    resource_id = new_resource_id(suffix)
    replace_stored_material(temporary, resource_id)
    return _to_normalized_material(
        probe,
        field_name=field_name,
        position=position,
        resource_id=resource_id,
    )


def _to_normalized_material(
    probe: MaterialProbe,
    *,
    field_name: str,
    position: int,
    resource_id: str,
) -> NormalizedInputMaterial:
    return NormalizedInputMaterial(
        field_name=field_name,
        position=position,
        category=probe.category,
        resource_id=resource_id,
        content_sha256=probe.content_sha256,
        size_bytes=probe.size_bytes,
        duration_seconds=probe.duration_seconds,
        extras=dict(probe.extras),
    )


def _material_snapshot(material: NormalizedInputMaterial) -> dict[str, object]:
    return {
        "field_name": material.field_name,
        "position": material.position,
        "category": material.category,
        "resource_id": material.resource_id,
        "content_sha256": material.content_sha256,
        "size_bytes": material.size_bytes,
        "duration_seconds": None if material.duration_seconds is None else str(material.duration_seconds),
        "extras": dict(material.extras),
    }


def _record_probe_facts(
    field_name: str,
    probe: MaterialProbe,
    *,
    image_counts: dict[str, int],
    image_dimensions: dict[str, list[tuple[int, int]]],
    image_tokens: dict[str, Decimal],
    video_seconds: dict[str, Decimal],
    audio_seconds: dict[str, Decimal],
) -> None:
    if probe.category == "image":
        image_counts[field_name] += 1
        width = probe.extras.get("width")
        height = probe.extras.get("height")
        if isinstance(width, int) and isinstance(height, int):
            image_dimensions[field_name].append((width, height))
            image_tokens[field_name] += Decimal(width * height) / Decimal(1024)
    elif probe.category == "video" and probe.duration_seconds is not None:
        video_seconds[field_name] += probe.duration_seconds
    elif probe.category == "audio" and probe.duration_seconds is not None:
        audio_seconds[field_name] += probe.duration_seconds


def _public_material_snapshot(field_name: str, position: int, probe: MaterialProbe) -> dict[str, object]:
    return {
        "field_name": field_name,
        "position": position,
        "category": probe.category,
        "content_sha256": probe.content_sha256,
        "size_bytes": probe.size_bytes,
        "duration_seconds": None if probe.duration_seconds is None else str(probe.duration_seconds),
        "extras": dict(probe.extras),
    }
