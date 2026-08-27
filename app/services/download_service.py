"""图片下载历史与累计计数事务。

下载记录保存标题和地址快照，之后即使图片资料变化，历史页面仍能展示当时内容；
删除历史使用软删除且不会回退累计业务计数。
"""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import not_found
from app.models.behavior import DownloadRecord
from app.models.user import User, UserStat
from app.services.image_access_service import require_public_image
from app.services.log_service import write_log
from app.utils.image_url import normalize_image_url
from app.utils.pagination import normalize_pagination, pagination_payload


async def create_download(
    db: AsyncSession,
    *,
    user: User,
    image_id: int,
    ip_address: str | None,
) -> dict:
    """创建下载快照，并在同一事务内更新图片和用户累计下载数。"""
    image = await require_public_image(
        db,
        image_id,
        error_message="图片不存在或暂未公开，无法下载",
        for_update=True,
    )
    stats = await db.scalar(select(UserStat).where(UserStat.user_id == user.id).with_for_update())
    download_url = normalize_image_url(image.image_url)
    db.add(
        DownloadRecord(
            user_id=user.id,
            image_id=image.id,
            image_title=image.title,
            image_url=download_url,
        )
    )
    image.download_count += 1
    if stats:
        stats.download_count += 1
    await write_log(
        db,
        actor=user,
        action_type="DOWNLOAD_IMAGE",
        target_type="download",
        target_id=image.id,
        title="下载图片",
        content=f"{user.username} 下载了图片《{image.title}》",
        ip_address=ip_address,
    )
    await db.commit()
    return {
        "image_id": image.id,
        "download_url": download_url,
        "download_count": image.download_count,
    }


async def list_downloads(
    db: AsyncSession,
    *,
    user_id: int,
    page: int,
    page_size: int,
) -> dict:
    """分页返回用户尚未删除的下载快照。"""
    page, page_size, offset = normalize_pagination(page, page_size)
    conditions = [
        DownloadRecord.user_id == user_id,
        DownloadRecord.deleted_at.is_(None),
    ]
    total = await db.scalar(select(func.count()).select_from(DownloadRecord).where(*conditions)) or 0
    records = (
        await db.scalars(
            select(DownloadRecord)
            .where(*conditions)
            .order_by(DownloadRecord.created_at.desc(), DownloadRecord.id.desc())
            .offset(offset)
            .limit(page_size)
        )
    ).all()
    return {
        "list": [
            {
                "id": record.id,
                "image_id": record.image_id,
                "image_title": record.image_title,
                "image_url": normalize_image_url(record.image_url),
                "created_at": record.created_at,
            }
            for record in records
        ],
        "pagination": pagination_payload(
            page=page,
            page_size=page_size,
            total=total,
        ),
    }


async def delete_download(
    db: AsyncSession,
    *,
    user: User,
    record_id: int,
    ip_address: str | None,
) -> dict:
    """软删除当前用户的一条下载记录，不回退累计下载数。"""
    record = await db.scalar(
        select(DownloadRecord)
        .where(
            DownloadRecord.id == record_id,
            DownloadRecord.user_id == user.id,
            DownloadRecord.deleted_at.is_(None),
        )
        .with_for_update()
    )
    if not record:
        raise not_found("下载记录不存在或已删除")

    record.deleted_at = datetime.now()
    await write_log(
        db,
        actor=user,
        action_type="DOWNLOAD_RECORD_DELETE",
        target_type="download",
        target_id=record.id,
        title="删除下载记录",
        content=f"{user.username} 删除了一条下载记录",
        ip_address=ip_address,
    )
    await db.commit()
    return {}


async def clear_downloads(
    db: AsyncSession,
    *,
    user: User,
    ip_address: str | None,
) -> dict:
    """软删除当前用户全部下载记录，清空操作保持幂等。"""
    records = (
        await db.scalars(
            select(DownloadRecord)
            .where(
                DownloadRecord.user_id == user.id,
                DownloadRecord.deleted_at.is_(None),
            )
            .with_for_update()
        )
    ).all()
    deleted_at = datetime.now()
    for record in records:
        record.deleted_at = deleted_at
    await write_log(
        db,
        actor=user,
        action_type="DOWNLOAD_RECORD_CLEAR",
        target_type="download",
        target_id=None,
        title="清空下载记录",
        content=f"{user.username} 清空了下载记录",
        ip_address=ip_address,
    )
    await db.commit()
    return {}
