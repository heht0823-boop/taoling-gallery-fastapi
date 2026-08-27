import asyncio
import ipaddress
import socket
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from uuid import uuid4

import httpx
from fastapi import UploadFile
from PIL import Image as PILImage

from app.core.config import settings
from app.core.exceptions import bad_request
from app.services.image_variant_service import ensure_variant

ALLOWED_AVATAR_TYPES = {
    "image/jpeg": (".jpg", "JPEG"),
    "image/png": (".png", "PNG"),
    "image/webp": (".webp", "WEBP"),
}
REMOTE_REDIRECT_LIMIT = 3


@dataclass(frozen=True)
class AvatarAsset:
    avatar_url: str
    thumbnail_url: str | None
    srcset: str | None
    processor_enabled: bool
    paths: tuple[Path, ...]


def public_upload_url(path: Path) -> str:
    relative = path.resolve().relative_to(settings.upload_path.resolve())
    return f"{settings.app_url.rstrip('/')}/uploads/{relative.as_posix()}"


def _validate_image(path: Path, expected_format: str) -> None:
    try:
        with PILImage.open(path) as image:
            actual_format = str(image.format or "").upper()
            image.verify()
    except (OSError, ValueError) as exc:
        raise bad_request("头像文件不是有效图片") from exc
    if actual_format != expected_format:
        raise bad_request("头像文件内容与文件类型不匹配")


async def _write_chunks(
    chunks: AsyncIterator[bytes],
    *,
    content_type: str,
) -> Path:
    type_config = ALLOWED_AVATAR_TYPES.get(content_type.lower())
    if not type_config:
        raise bad_request("头像仅支持 jpg、png、webp 图片")
    extension, expected_format = type_config
    max_size = settings.upload_max_size_mb * 1024 * 1024
    settings.upload_path.mkdir(parents=True, exist_ok=True)
    target = settings.upload_path / f"avatar-{uuid4().hex}{extension}"
    size = 0
    try:
        with target.open("xb") as output:
            async for chunk in chunks:
                size += len(chunk)
                if size > max_size:
                    raise bad_request(
                        f"头像文件不能超过 {settings.upload_max_size_mb}MB"
                    )
                output.write(chunk)
        if size == 0:
            raise bad_request("头像文件不能为空")
        await asyncio.to_thread(_validate_image, target, expected_format)
        return target
    except Exception:
        target.unlink(missing_ok=True)
        raise


async def _upload_chunks(file: UploadFile) -> AsyncIterator[bytes]:
    while chunk := await file.read(1024 * 1024):
        yield chunk


def _ensure_public_ip(address: str) -> None:
    parsed = ipaddress.ip_address(address)
    if not parsed.is_global:
        raise bad_request("头像外链不能指向本机或内网地址")


async def _validate_remote_url(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise bad_request("头像外链必须是有效的 http 或 https 地址")
    try:
        direct_ip = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        try:
            addresses = await asyncio.to_thread(
                socket.getaddrinfo,
                parsed.hostname,
                parsed.port or (443 if parsed.scheme == "https" else 80),
                type=socket.SOCK_STREAM,
            )
        except OSError as exc:
            raise bad_request("头像外链域名无法解析") from exc
        for address in {item[4][0] for item in addresses}:
            _ensure_public_ip(address)
    else:
        _ensure_public_ip(str(direct_ip))


async def _download_remote_avatar(url: str) -> Path:
    current_url = url.strip()
    async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
        for _ in range(REMOTE_REDIRECT_LIMIT + 1):
            await _validate_remote_url(current_url)
            try:
                async with client.stream("GET", current_url) as response:
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location:
                            raise bad_request("头像外链重定向地址无效")
                        current_url = urljoin(current_url, location)
                        continue
                    if not response.is_success:
                        raise bad_request("头像外链下载失败，请更换后重试")
                    content_type = response.headers.get("content-type", "").split(
                        ";", maxsplit=1
                    )[0]
                    return await _write_chunks(
                        response.aiter_bytes(),
                        content_type=content_type,
                    )
            except httpx.HTTPError as exc:
                raise bad_request("头像外链下载失败，请更换后重试") from exc
    raise bad_request("头像外链重定向次数过多")


async def store_avatar(
    *,
    file: UploadFile | None,
    remote_url: str | None,
) -> AvatarAsset:
    """保存头像源文件并生成 80/160 像素展示变体。"""
    if file:
        source = await _write_chunks(
            _upload_chunks(file),
            content_type=file.content_type or "",
        )
    elif remote_url and remote_url.strip():
        source = await _download_remote_avatar(remote_url)
    else:
        raise bad_request("请上传头像文件或提交 avatar_url")

    generated_paths: list[Path] = []
    try:
        small, _ = await ensure_variant(
            source,
            width=80,
            image_format=settings.image_optimizer_format,
            quality=settings.image_optimizer_quality,
        )
        generated_paths.append(small)
        large, _ = await ensure_variant(
            source,
            width=160,
            image_format=settings.image_optimizer_format,
            quality=settings.image_optimizer_quality,
        )
        generated_paths.append(large)
    except Exception:
        source.unlink(missing_ok=True)
        for path in generated_paths:
            path.unlink(missing_ok=True)
        raise

    small_url = public_upload_url(small)
    large_url = public_upload_url(large)
    return AvatarAsset(
        avatar_url=public_upload_url(source),
        thumbnail_url=small_url,
        srcset=f"{small_url} 1x, {large_url} 2x",
        processor_enabled=True,
        paths=(source, small, large),
    )


def remove_avatar_asset(asset: AvatarAsset) -> None:
    """删除本次请求新建的头像文件，用于数据库保存失败后的补偿。"""
    for path in asset.paths:
        path.unlink(missing_ok=True)
