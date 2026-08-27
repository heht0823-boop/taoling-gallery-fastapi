import asyncio
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile
from PIL import Image as PILImage
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import bad_request, not_found
from app.models.image import Category, Image, ImageTag, Tag
from app.models.user import User
from app.services.image_variant_service import ensure_variant
from app.services.log_service import write_log
from app.utils.image_url import image_thumbnail_url, normalize_image_url
from app.utils.pagination import normalize_pagination, pagination_payload

ALLOWED_IMAGE_TYPES = {
    "image/jpeg": (".jpg", "JPEG"),
    "image/png": (".png", "PNG"),
    "image/webp": (".webp", "WEBP"),
}
ALLOWED_STATUSES = {"public", "private", "draft", "deleted"}


def _public_upload_url(path: Path) -> str:
    relative = path.resolve().relative_to(settings.upload_path.resolve())
    return f"{settings.app_url.rstrip('/')}/uploads/{relative.as_posix()}"


def _verify_image(path: Path, expected_format: str) -> None:
    try:
        with PILImage.open(path) as image:
            actual_format = str(image.format or "").upper()
            image.verify()
    except (OSError, SyntaxError, ValueError) as exc:
        raise bad_request("上传文件不是有效图片") from exc
    if actual_format != expected_format:
        raise bad_request("图片文件内容与文件类型不匹配")


async def upload_image(file: UploadFile | None) -> dict:
    if not file:
        raise bad_request("请上传图片文件")
    type_config = ALLOWED_IMAGE_TYPES.get((file.content_type or "").lower())
    if not type_config:
        raise bad_request("图片仅支持 jpg、png、webp 格式")
    extension, expected_format = type_config
    settings.upload_path.mkdir(parents=True, exist_ok=True)
    source = settings.upload_path / f"image-{uuid4().hex}{extension}"
    max_size = settings.upload_max_size_mb * 1024 * 1024
    size = 0
    generated: list[Path] = []
    try:
        with source.open("xb") as output:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > max_size:
                    raise bad_request(
                        f"图片文件不能超过 {settings.upload_max_size_mb}MB"
                    )
                output.write(chunk)
        if not size:
            raise bad_request("图片文件不能为空")
        await asyncio.to_thread(_verify_image, source, expected_format)
        thumbnail, _ = await ensure_variant(
            source,
            width=settings.image_thumbnail_width,
            image_format=settings.image_optimizer_format,
            quality=settings.image_optimizer_quality,
        )
        generated.append(thumbnail)
        large, _ = await ensure_variant(
            source,
            width=520,
            image_format=settings.image_optimizer_format,
            quality=settings.image_optimizer_quality,
        )
        generated.append(large)
    except Exception:
        source.unlink(missing_ok=True)
        for path in generated:
            path.unlink(missing_ok=True)
        raise
    source_url = _public_upload_url(source)
    thumbnail_url = _public_upload_url(thumbnail)
    large_url = _public_upload_url(large)
    return {
        "image_url": source_url,
        "thumbnail_url": thumbnail_url,
        "thumbnail_srcset": f"{thumbnail_url} 420w, {large_url} 520w",
        "variants": [
            {"width": settings.image_thumbnail_width, "url": thumbnail_url},
            {"width": 520, "url": large_url},
        ],
        "processor_enabled": True,
    }


def _normalize_tag_ids(values: list[int] | None) -> list[int]:
    return sorted({int(value) for value in values or [] if int(value) > 0})


async def _validate_category(db: AsyncSession, category_id: int | None) -> None:
    if category_id is None:
        return
    exists = await db.scalar(
        select(Category.id).where(
            Category.id == category_id,
            Category.deleted_at.is_(None),
        )
    )
    if not exists:
        raise bad_request("分类不存在")


async def _sync_tags(
    db: AsyncSession,
    *,
    image_id: int,
    tag_ids: list[int],
) -> None:
    next_ids = set(_normalize_tag_ids(tag_ids))
    if next_ids:
        found = set(
            (
                await db.scalars(
                    select(Tag.id).where(
                        Tag.id.in_(next_ids),
                        Tag.deleted_at.is_(None),
                    )
                )
            ).all()
        )
        if found != next_ids:
            raise bad_request("存在无效标签")
    current_rows = list(
        (
            await db.scalars(select(ImageTag).where(ImageTag.image_id == image_id))
        ).all()
    )
    current_ids = {row.tag_id for row in current_rows}
    add_ids = next_ids - current_ids
    remove_ids = current_ids - next_ids
    for row in current_rows:
        if row.tag_id in remove_ids:
            await db.delete(row)
    for tag_id in add_ids:
        db.add(ImageTag(image_id=image_id, tag_id=tag_id))
    if add_ids:
        await db.execute(
            update(Tag)
            .where(Tag.id.in_(add_ids))
            .values(usage_count=Tag.usage_count + 1)
        )
    if remove_ids:
        await db.execute(
            update(Tag)
            .where(Tag.id.in_(remove_ids))
            .values(usage_count=func.greatest(Tag.usage_count - 1, 0))
        )


async def _load_context(
    db: AsyncSession,
    images: list[Image],
) -> tuple[dict[int, Category], dict[int, list[Tag]]]:
    category_ids = {image.category_id for image in images if image.category_id}
    category_map: dict[int, Category] = {}
    if category_ids:
        categories = list(
            (await db.scalars(select(Category).where(Category.id.in_(category_ids)))).all()
        )
        category_map = {category.id: category for category in categories}
    tags_by_image: dict[int, list[Tag]] = {image.id: [] for image in images}
    image_ids = [image.id for image in images]
    if image_ids:
        tag_rows = (
            await db.execute(
                select(ImageTag.image_id, Tag)
                .join(Tag, Tag.id == ImageTag.tag_id)
                .where(ImageTag.image_id.in_(image_ids))
                .order_by(Tag.usage_count.desc(), Tag.created_at.desc())
            )
        ).all()
        for image_id, tag in tag_rows:
            tags_by_image[image_id].append(tag)
    return category_map, tags_by_image


def _serialize_image(
    image: Image,
    *,
    category: Category | None,
    tags: list[Tag],
) -> dict:
    return {
        "id": image.id,
        "title": image.title,
        "description": image.description,
        "image_url": normalize_image_url(image.image_url),
        "thumbnail_url": image_thumbnail_url(image),
        "aspect_ratio": image.aspect_ratio,
        "category": (
            {"id": category.id, "name": category.name} if category else None
        ),
        "tags": [
            {"id": tag.id, "name": tag.name, "color": tag.color}
            for tag in tags
        ],
        "view_count": image.view_count,
        "download_count": image.download_count,
        "favorite_count": image.favorite_count,
        "is_favorited": False,
        "created_at": image.created_at,
        "status": image.status,
        "display_weight": image.display_weight,
        "deleted_at": image.deleted_at,
        "tag_ids": [tag.id for tag in tags],
    }


async def get_image(db: AsyncSession, image_id: int) -> dict:
    image = await db.scalar(select(Image).where(Image.id == image_id))
    if not image:
        raise not_found("图片不存在")
    category_map, tags_by_image = await _load_context(db, [image])
    return _serialize_image(
        image,
        category=category_map.get(image.category_id),
        tags=tags_by_image.get(image.id, []),
    )


async def list_images(
    db: AsyncSession,
    *,
    page: int,
    page_size: int,
    keyword: str | None,
    category_id: int | None,
    status: str | None,
    tag_id: int | None,
    sort: str | None,
) -> dict:
    page, page_size, offset = normalize_pagination(page, page_size)
    conditions = []
    if status == "deleted":
        conditions.append(
            or_(Image.status == "deleted", Image.deleted_at.is_not(None))
        )
    else:
        conditions.append(Image.deleted_at.is_(None))
        if status:
            conditions.append(Image.status == status)
    if category_id is not None:
        conditions.append(Image.category_id == category_id)
    if keyword and (value := keyword.strip()):
        search = f"%{value}%"
        tag_match = (
            select(ImageTag.image_id)
            .join(Tag, Tag.id == ImageTag.tag_id)
            .where(Tag.name.like(search), Tag.deleted_at.is_(None))
        )
        conditions.append(
            or_(
                Image.title.like(search),
                Image.description.like(search),
                Image.id.in_(tag_match),
            )
        )
    if tag_id:
        conditions.append(
            Image.id.in_(select(ImageTag.image_id).where(ImageTag.tag_id == tag_id))
        )
    order_map = {
        "latest": (Image.created_at.desc(),),
        "views": (Image.view_count.desc(), Image.created_at.desc()),
        "downloads": (Image.download_count.desc(), Image.created_at.desc()),
        "favorites": (Image.favorite_count.desc(), Image.created_at.desc()),
        "weight": (Image.display_weight.desc(), Image.created_at.desc()),
    }
    order_by = order_map.get(sort or "", order_map["latest"])
    total = await db.scalar(
        select(func.count()).select_from(Image).where(*conditions)
    ) or 0
    images = list(
        (
            await db.scalars(
                select(Image)
                .where(*conditions)
                .order_by(*order_by)
                .offset(offset)
                .limit(page_size)
            )
        ).all()
    )
    category_map, tags_by_image = await _load_context(db, images)
    return {
        "list": [
            _serialize_image(
                image,
                category=category_map.get(image.category_id),
                tags=tags_by_image.get(image.id, []),
            )
            for image in images
        ],
        "pagination": pagination_payload(
            page=page,
            page_size=page_size,
            total=total,
        ),
    }


async def create_image(
    db: AsyncSession,
    *,
    admin: User,
    payload: dict,
    ip_address: str | None,
) -> dict:
    title = str(payload.get("title") or "").strip()
    image_url = str(payload.get("image_url") or "").strip()
    if not title:
        raise bad_request("title 不能为空")
    if not image_url:
        raise bad_request("image_url 不能为空")
    status = payload.get("status") or "draft"
    if status not in ALLOWED_STATUSES:
        raise bad_request("图片状态只能是 public、private、draft、deleted")
    await _validate_category(db, payload.get("category_id"))
    image = Image(
        title=title,
        description=payload.get("description") or None,
        image_url=normalize_image_url(image_url),
        thumbnail_url=normalize_image_url(payload.get("thumbnail_url")) or None,
        category_id=payload.get("category_id"),
        aspect_ratio=payload.get("aspect_ratio") or None,
        status=status,
        display_weight=payload.get("display_weight") or 0,
        deleted_at=datetime.now() if status == "deleted" else None,
    )
    db.add(image)
    await db.flush()
    await _sync_tags(db, image_id=image.id, tag_ids=payload.get("tag_ids") or [])
    await write_log(
        db,
        actor=admin,
        action_type="IMAGE_UPLOAD",
        target_type="image",
        target_id=image.id,
        title="上传图片",
        content=f"{admin.username} 创建了图片《{image.title}》",
        ip_address=ip_address,
    )
    await db.commit()
    return await get_image(db, image.id)


async def update_image(
    db: AsyncSession,
    *,
    admin: User,
    image_id: int,
    payload: dict,
    ip_address: str | None,
) -> dict:
    image = await db.scalar(select(Image).where(Image.id == image_id))
    if not image:
        raise not_found("图片不存在")
    if payload.get("status") and payload["status"] not in ALLOWED_STATUSES:
        raise bad_request("图片状态只能是 public、private、draft、deleted")
    if "category_id" in payload:
        await _validate_category(db, payload.get("category_id"))
    for field in (
        "title",
        "description",
        "aspect_ratio",
        "status",
        "display_weight",
        "category_id",
    ):
        if field in payload:
            setattr(image, field, payload[field])
    for field in ("image_url", "thumbnail_url"):
        if field in payload:
            setattr(image, field, normalize_image_url(payload[field]) or None)
    if not str(image.title or "").strip():
        raise bad_request("title 不能为空")
    if not str(image.image_url or "").strip():
        raise bad_request("image_url 不能为空")
    if "status" in payload:
        image.deleted_at = datetime.now() if image.status == "deleted" else None
    if "tag_ids" in payload:
        await _sync_tags(
            db,
            image_id=image.id,
            tag_ids=payload.get("tag_ids") or [],
        )
    await write_log(
        db,
        actor=admin,
        action_type="IMAGE_UPDATE",
        target_type="image",
        target_id=image.id,
        title="编辑图片",
        content=f"{admin.username} 编辑了图片《{image.title}》",
        ip_address=ip_address,
    )
    await db.commit()
    return await get_image(db, image.id)


async def change_status(
    db: AsyncSession,
    *,
    admin: User,
    image_id: int,
    status: str,
    ip_address: str | None,
) -> dict:
    if status not in ALLOWED_STATUSES:
        raise bad_request("图片状态只能是 public、private、draft、deleted")
    image = await db.scalar(select(Image).where(Image.id == image_id))
    if not image:
        raise not_found("图片不存在")
    image.status = status
    image.deleted_at = datetime.now() if status == "deleted" else None
    await write_log(
        db,
        actor=admin,
        action_type="IMAGE_STATUS_CHANGE",
        target_type="image",
        target_id=image.id,
        title="修改图片状态",
        content=f"{admin.username} 将图片《{image.title}》状态改为 {status}",
        ip_address=ip_address,
    )
    await db.commit()
    return await get_image(db, image.id)


async def delete_image(
    db: AsyncSession,
    *,
    admin: User,
    image_id: int,
    ip_address: str | None,
) -> dict:
    image = await db.scalar(select(Image).where(Image.id == image_id))
    if not image:
        raise not_found("图片不存在")
    image.status = "deleted"
    image.deleted_at = datetime.now()
    await write_log(
        db,
        actor=admin,
        action_type="IMAGE_DELETE",
        target_type="image",
        target_id=image.id,
        title="删除图片",
        content=f"{admin.username} 删除了图片《{image.title}》",
        ip_address=ip_address,
    )
    await db.commit()
    return {}


async def restore_image(
    db: AsyncSession,
    *,
    admin: User,
    image_id: int,
    status: str,
    ip_address: str | None,
) -> dict:
    if status not in {"draft", "private", "public"}:
        raise bad_request("恢复后的状态只能是 draft、private、public")
    image = await db.scalar(select(Image).where(Image.id == image_id))
    if not image:
        raise not_found("图片不存在")
    image.status = status
    image.deleted_at = None
    await write_log(
        db,
        actor=admin,
        action_type="IMAGE_RESTORE",
        target_type="image",
        target_id=image.id,
        title="恢复图片",
        content=f"{admin.username} 恢复了图片《{image.title}》",
        ip_address=ip_address,
    )
    await db.commit()
    return await get_image(db, image.id)
