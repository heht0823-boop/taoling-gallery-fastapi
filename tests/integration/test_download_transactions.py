import pytest
from sqlalchemy import func, select

from app.core.exceptions import AppError
from app.models.behavior import DownloadRecord
from app.services.download_service import (
    clear_downloads,
    create_download,
    delete_download,
    list_downloads,
)


async def test_download_service_keeps_cumulative_counts_after_soft_delete(
    behavior_records,
):
    db, user, stats, image, *_ = behavior_records
    before_image = image.download_count
    before_user = stats.download_count

    created = await create_download(
        db,
        user=user,
        image_id=image.id,
        ip_address="127.0.0.1",
    )
    page = await list_downloads(db, user_id=user.id, page=1, page_size=12)
    record_id = page["list"][0]["id"]
    await db.refresh(image)
    await db.refresh(stats)

    assert created == {
        "image_id": image.id,
        "download_url": image.image_url,
        "download_count": before_image + 1,
    }
    assert page["pagination"]["totalPages"] == 1
    assert page["list"][0]["image_title"] == image.title
    assert image.download_count == before_image + 1
    assert stats.download_count == before_user + 1

    await delete_download(
        db,
        user=user,
        record_id=record_id,
        ip_address="127.0.0.1",
    )
    with pytest.raises(AppError) as exc_info:
        await delete_download(
            db,
            user=user,
            record_id=record_id,
            ip_address="127.0.0.1",
        )
    assert exc_info.value.status_code == 404

    await create_download(
        db,
        user=user,
        image_id=image.id,
        ip_address="127.0.0.1",
    )
    await create_download(
        db,
        user=user,
        image_id=image.id,
        ip_address="127.0.0.1",
    )
    await clear_downloads(db, user=user, ip_address="127.0.0.1")
    empty_page = await list_downloads(db, user_id=user.id, page=1, page_size=12)
    active_count = await db.scalar(
        select(func.count())
        .select_from(DownloadRecord)
        .where(
            DownloadRecord.user_id == user.id,
            DownloadRecord.deleted_at.is_(None),
        )
    )
    await db.refresh(image)
    await db.refresh(stats)

    assert empty_page["pagination"]["total"] == 0
    assert active_count == 0
    assert image.download_count == before_image + 3
    assert stats.download_count == before_user + 3


async def test_download_http_and_compatibility_routes(
    authenticated_client,
    behavior_records,
):
    _, _, _, image, *_ = behavior_records
    created = await authenticated_client.post(f"/api/images/{image.id}/download")
    downloads = await authenticated_client.get(
        "/api/user/downloads",
        params={"page": 1, "pageSize": 12},
    )
    record_id = downloads.json()["data"]["list"][0]["id"]
    removed = await authenticated_client.delete(f"/api/user/downloads/{record_id}")
    alias_created = await authenticated_client.post(
        "/api/user/downloads",
        json={"imageId": image.id},
    )
    cleared = await authenticated_client.delete("/api/user/downloads")

    assert created.status_code == 201
    assert created.json()["data"]["download_url"] == image.image_url
    assert downloads.status_code == 200
    assert downloads.json()["data"]["pagination"]["total"] == 1
    assert removed.json()["message"] == "下载记录已删除"
    assert alias_created.status_code == 201
    assert cleared.json()["message"] == "下载记录已清空"
