import re
from typing import Any
from urllib.parse import quote, unquote, urlsplit

from app.core.config import settings


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
    return re.sub(
        r"\{(\w+)\}",
        lambda match: quote(str(values.get(match.group(1), "")), safe=""),
        template,
    )


def _append_query(url: str, query: str) -> str:
    if not query:
        return url
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}{query.lstrip('?')}"


def _local_variant_url(url: str, *, width: int, image_format: str, quality: int) -> str:
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
