from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import not_found
from app.models.image import Image


async def require_public_image(
    db: AsyncSession,
    image_id: int,
    *,
    error_message: str = "图片不存在或暂未公开",
    for_update: bool = False,
) -> Image:
    """读取公开且未删除的图片，可选加行锁供计数事务使用。"""
    statement = select(Image).where(
        Image.id == image_id,
        Image.status == "public",
        Image.deleted_at.is_(None),
    )
    if for_update:
        statement = statement.with_for_update()
    image = await db.scalar(statement)
    if not image:
        raise not_found(error_message)
    return image
