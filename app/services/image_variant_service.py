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
    try:
        width = int(value or fallback)
    except (TypeError, ValueError):
        return fallback
    return min(max(width, 32), 2000)


def sanitize_quality(value: int | str | None) -> int:
    try:
        quality = int(value or settings.image_optimizer_quality)
    except (TypeError, ValueError):
        return settings.image_optimizer_quality
    return min(max(quality, 35), 95)


def sanitize_format(value: str | None) -> str:
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
    target = settings.upload_path / "variants" / _variant_filename(
        source,
        width=safe_width,
        image_format=safe_format,
        quality=safe_quality,
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
