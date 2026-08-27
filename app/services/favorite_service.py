"""图片收藏的幂等事务与列表查询。

收藏明细、图片累计数、用户统计和管理员审计日志在同一事务提交；重复添加或
重复取消不会导致计数漂移。
"""

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import conflict
from app.models.behavior import Favorite
from app.models.image import Image
from app.models.user import User, UserStat
from app.services.image_access_service import require_public_image
from app.services.log_service import write_log
from app.utils.image_url import image_thumbnail_url, normalize_image_url
from app.utils.pagination import normalize_pagination, pagination_payload


async def add_favorite(
    db: AsyncSession,
    *,
    user: User,
    image_id: int,
    ip_address: str | None,
) -> dict:
    """新增收藏，并在同一事务内更新图片、用户统计和审计日志。"""
    image = await require_public_image(
        db,
        image_id,
        error_message="图片不存在或暂未公开，无法收藏",
        for_update=True,
    )
    favorite = await db.scalar(
        select(Favorite).where(
            Favorite.user_id == user.id,
            Favorite.image_id == image.id,
        )
    )
    if favorite:
        raise conflict("你已经收藏过这张图片")

    stats = await db.scalar(select(UserStat).where(UserStat.user_id == user.id).with_for_update())
    db.add(Favorite(user_id=user.id, image_id=image.id))
    image.favorite_count += 1
    if stats:
        stats.favorite_count += 1
    await write_log(
        db,
        actor=user,
        action_type="FAVORITE_CREATE",
        target_type="favorite",
        target_id=image.id,
        title="收藏图片",
        content=f"{user.username} 收藏了图片《{image.title}》",
        ip_address=ip_address,
    )
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise conflict("你已经收藏过这张图片") from exc

    return {
        "image_id": image.id,
        "is_favorited": True,
        "favorite_count": image.favorite_count,
    }


async def remove_favorite(
    db: AsyncSession,
    *,
    user: User,
    image_id: int,
    ip_address: str | None,
) -> dict:
    """取消收藏；未收藏时直接返回当前状态，保持接口幂等。"""
    image = await require_public_image(
        db,
        image_id,
        error_message="图片不存在或暂未公开，无法取消收藏",
        for_update=True,
    )
    favorite = await db.scalar(
        select(Favorite).where(
            Favorite.user_id == user.id,
            Favorite.image_id == image.id,
        )
    )
    if not favorite:
        return {
            "image_id": image.id,
            "is_favorited": False,
            "favorite_count": image.favorite_count,
        }

    stats = await db.scalar(select(UserStat).where(UserStat.user_id == user.id).with_for_update())
    await db.delete(favorite)
    image.favorite_count = max(image.favorite_count - 1, 0)
    if stats:
        stats.favorite_count = max(stats.favorite_count - 1, 0)
    await write_log(
        db,
        actor=user,
        action_type="FAVORITE_CANCEL",
        target_type="favorite",
        target_id=image.id,
        title="取消收藏",
        content=f"{user.username} 取消收藏图片《{image.title}》",
        ip_address=ip_address,
    )
    await db.commit()
    return {
        "image_id": image.id,
        "is_favorited": False,
        "favorite_count": image.favorite_count,
    }


async def list_favorites(
    db: AsyncSession,
    *,
    user_id: int,
    page: int,
    page_size: int,
) -> dict:
    """返回当前用户仍可访问的公开图片收藏记录。"""
    page, page_size, offset = normalize_pagination(page, page_size)
    conditions = [
        Favorite.user_id == user_id,
        Image.status == "public",
        Image.deleted_at.is_(None),
    ]
    total = (
        await db.scalar(
            select(func.count())
            .select_from(Favorite)
            .join(Image, Image.id == Favorite.image_id)
            .where(*conditions)
        )
        or 0
    )
    rows = await db.execute(
        select(Favorite, Image)
        .join(Image, Image.id == Favorite.image_id)
        .where(*conditions)
        .order_by(Favorite.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    return {
        "list": [
            {
                "favorite_id": favorite.id,
                "created_at": favorite.created_at,
                "image": {
                    "id": image.id,
                    "title": image.title,
                    "thumbnail_url": image_thumbnail_url(image),
                    "image_url": normalize_image_url(image.image_url),
                    "view_count": image.view_count,
                    "download_count": image.download_count,
                    "favorite_count": image.favorite_count,
                },
            }
            for favorite, image in rows.all()
        ],
        "pagination": pagination_payload(
            page=page,
            page_size=page_size,
            total=total,
        ),
    }
