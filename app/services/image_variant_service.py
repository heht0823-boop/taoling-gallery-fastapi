"""本地上传图片的缩略图参数清洗与缓存文件生成。

URL 到路径的转换强制限制在上传根目录，宽度、质量和格式均使用白名单/边界值，
生成工作在线程中执行以避免阻塞 FastAPI 事件循环。
"""

import asyncio
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

from PIL import Image as PILImage
from PIL import ImageOps

from app.core.config import settings
from app.core.exceptions import bad_request, not_found

ALLOWED_FORMATS = {"webp", "avif", "jpg", "jpeg", "png"}


def sanitize_width(value: int | str | None, fallback: int = 420) -> int:
    """把缩略图宽度限制在服务支持的安全范围内。"""

    try:
        width = int(value or fallback)
    except (TypeError, ValueError):
        return fallback
    return min(max(width, 32), 2000)


def sanitize_quality(value: int | str | None) -> int:
    """把图片质量限制在兼顾体积和清晰度的范围内。"""

    try:
        quality = int(value or settings.image_optimizer_quality)
    except (TypeError, ValueError):
        return settings.image_optimizer_quality
    return min(max(quality, 35), 95)


def sanitize_format(value: str | None) -> str:
    """规范输出格式并拒绝不支持的图片编码。"""

    image_format = str(value or settings.image_optimizer_format).lower()
    return image_format if image_format in ALLOWED_FORMATS else "webp"


def local_upload_path_from_url(url: str | None) -> Path | None:
    """把 /uploads URL 安全解析到上传根目录，拒绝目录穿越。"""
    path = unquote(urlsplit(str(url or "")).path)
    marker = "/uploads/"
    if marker not in path:
        return None

    relative = path.split(marker, maxsplit=1)[1]
    root = settings.upload_path.resolve()
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate


def _variant_filename(
    source: Path,
    *,
    width: int,
    image_format: str,
    quality: int,
) -> str:
    """构造稳定且可缓存的图片变体文件名。"""

    stem = re.sub(r"[^a-zA-Z0-9_-]", "", source.stem)
    extension = "jpg" if image_format == "jpeg" else image_format
    return f"{stem}-{width}w-q{quality}.{extension}"


def _write_variant(
    source: Path,
    target: Path,
    *,
    width: int,
    image_format: str,
    quality: int,
) -> None:
    """使用 Pillow 生成指定尺寸、格式和质量的变体文件。"""

    target.parent.mkdir(parents=True, exist_ok=True)
    with PILImage.open(source) as opened:
        image = ImageOps.exif_transpose(opened)
        image.thumbnail((width, width))
        if image_format in {"jpg", "jpeg"} and image.mode not in {"RGB", "L"}:
            image = image.convert("RGB")

        save_format = "JPEG" if image_format in {"jpg", "jpeg"} else image_format.upper()
        save_options = {"quality": quality}
        if save_format == "PNG":
            save_options = {"optimize": True}
        image.save(target, save_format, **save_options)


async def ensure_variant(
    source: Path,
    *,
    width: int | str | None,
    image_format: str | None,
    quality: int | str | None,
) -> tuple[Path, str]:
    """为本地上传图片生成可缓存的缩略图文件。"""
    if not source.is_file():
        raise not_found("图片原文件不存在")

    safe_width = sanitize_width(width, settings.image_thumbnail_width)
    safe_format = sanitize_format(image_format)
    safe_quality = sanitize_quality(quality)
    target = (
        settings.upload_path
        / "variants"
        / _variant_filename(
            source,
            width=safe_width,
            image_format=safe_format,
            quality=safe_quality,
        )
    )

    if not target.is_file():
        try:
            await asyncio.to_thread(
                _write_variant,
                source,
                target,
                width=safe_width,
                image_format=safe_format,
                quality=safe_quality,
            )
        except (OSError, ValueError) as exc:
            raise bad_request("图片文件无法处理") from exc

    content_type = f"image/{'jpeg' if safe_format in {'jpg', 'jpeg'} else safe_format}"
    return target, content_type
