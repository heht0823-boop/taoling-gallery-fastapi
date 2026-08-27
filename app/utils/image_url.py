"""原图、缩略图和头像变体 URL 的规范化工具。"""

import re
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urlsplit

from app.core.config import settings


def public_upload_url(path: Path) -> str:
    """把上传根目录内的文件路径转换成公开访问 URL。"""

    relative = path.resolve().relative_to(settings.upload_path.resolve())
    return f"{settings.app_url.rstrip('/')}/uploads/{relative.as_posix()}"


def normalize_image_url(url: str | None) -> str:
    """规范图片地址，并把项目内相对上传地址转换成可访问的绝对 URL。"""
    source = str(url or "").strip()
    if not source:
        return ""

    source = re.sub(r"/+([?#]|$)", r"\1", source)
    if source.startswith("/"):
        return f"{settings.app_url.rstrip('/')}/{source.lstrip('/')}"
    if source.startswith("uploads/"):
        return f"{settings.app_url.rstrip('/')}/{source}"
    return source


def _compile_template(template: str, values: dict[str, Any]) -> str:
    """安全替换图片处理模板中的命名占位符。"""

    return re.sub(
        r"\{(\w+)\}",
        lambda match: quote(str(values.get(match.group(1), "")), safe=""),
        template,
    )


def _append_query(url: str, query: str) -> str:
    """把图片处理参数追加到已有或空白查询字符串。"""

    if not query:
        return url
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}{query.lstrip('?')}"


def _local_variant_url(url: str, *, width: int, image_format: str, quality: int) -> str:
    """为本地上传的单层文件生成静态变体地址。"""

    path = unquote(urlsplit(url).path)
    marker = "/uploads/"
    if marker not in path:
        return ""

    filename = path.split(marker, maxsplit=1)[1]
    if not filename or "/" in filename or "\\" in filename:
        return ""

    stem = re.sub(r"[^a-zA-Z0-9_-]", "", filename.rsplit(".", maxsplit=1)[0])
    if not stem:
        return ""

    extension = "jpg" if image_format == "jpeg" else image_format
    return (
        f"{settings.app_url.rstrip('/')}/uploads/variants/"
        f"{stem}-{width}w-q{quality}.{extension}"
    )


def image_variant_url(
    url: str | None,
    *,
    width: int,
    height: int | None = None,
    image_format: str | None = None,
    quality: int | None = None,
) -> str:
    """按当前对象存储或本地缩略图配置生成展示变体地址。"""
    source = normalize_image_url(url)
    if not source:
        return ""

    safe_height = height or width
    safe_format = image_format or settings.image_optimizer_format
    safe_quality = quality or settings.image_optimizer_quality
    values = {
        "url": source,
        "width": width,
        "height": safe_height,
        "format": safe_format,
        "quality": safe_quality,
    }

    if settings.image_optimizer_url_template:
        return _compile_template(settings.image_optimizer_url_template, values)
    if settings.image_optimizer_query_template:
        return _append_query(
            source,
            _compile_template(settings.image_optimizer_query_template, values),
        )

    return _local_variant_url(
        source,
        width=width,
        image_format=safe_format,
        quality=safe_quality,
    ) or source


def image_dynamic_variant_url(
    image_id: int,
    *,
    width: int | None = None,
    image_format: str | None = None,
    quality: int | None = None,
) -> str:
    """生成通过动态缩略图接口访问的变体地址。"""

    safe_width = width or settings.image_thumbnail_width
    safe_format = image_format or settings.image_optimizer_format
    safe_quality = quality or settings.image_optimizer_quality
    return (
        f"{settings.app_url.rstrip('/')}/api/images/{image_id}/thumbnail"
        f"?w={safe_width}&format={quote(safe_format)}&q={safe_quality}"
    )


def image_thumbnail_url(image: Any, width: int | None = None) -> str:
    """优先使用已保存缩略图，否则返回后端动态缩略图端点。"""
    safe_width = width or settings.image_thumbnail_width
    image_url = normalize_image_url(image.image_url)
    thumbnail_url = normalize_image_url(image.thumbnail_url)
    if thumbnail_url and thumbnail_url != image_url:
        return image_variant_url(thumbnail_url, width=safe_width, height=safe_width)
    return image_dynamic_variant_url(image.id, width=safe_width)


def avatar_variants(avatar_url: str | None) -> dict[str, str | None]:
    """生成头像的 1x/2x 展示地址；无可用变体时返回空字段。"""
    source = normalize_image_url(avatar_url)
    if not source:
        return {
            "avatar_thumbnail_url": None,
            "avatar_srcset": None,
        }

    small = image_variant_url(source, width=80, height=80)
    large = image_variant_url(source, width=160, height=160)
    if small == source and large == source:
        return {
            "avatar_thumbnail_url": None,
            "avatar_srcset": None,
        }
    return {
        "avatar_thumbnail_url": small,
        "avatar_srcset": f"{small} 1x, {large} 2x" if small and large else None,
    }
