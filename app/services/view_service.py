from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import not_found
from app.models.behavior import ImageViewRecord
from app.models.image import Image
from app.models.user import UserStat


async def record_view(
    db: AsyncSession,
    *,
    image_id: int,
    user_id: int | None,
    visitor_id: str | None,
    ip_address: str | None,
    user_agent: str | None,
) -> dict:
    """在一个事务中记录浏览明细，并同步图片与用户累计浏览数。"""
    image = await db.scalar(
        select(Image)
        .where(
            Image.id == image_id,
            Image.status == "public",
            Image.deleted_at.is_(None),
        )
        .with_for_update()
    )
    if not image:
        raise not_found("图片不存在或暂未公开，无法记录浏览")

    stats = None
    if user_id:
        stats = await db.scalar(
            select(UserStat)
            .where(UserStat.user_id == user_id)
            .with_for_update()
        )

    db.add(
        ImageViewRecord(
            user_id=user_id,
            image_id=image.id,
            visitor_id=visitor_id,
            image_title=image.title,
            ip_address=(ip_address or "")[:64] or None,
            user_agent=(user_agent or "")[:500] or None,
        )
    )
    image.view_count += 1
    if stats:
        stats.view_count += 1

    await db.commit()
    return {"image_id": image.id, "view_count": image.view_count}
