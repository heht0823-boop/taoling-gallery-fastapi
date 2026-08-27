from sqlalchemy import func, select

from app.models.behavior import ImageViewRecord
from app.services.view_service import record_view


async def test_record_view_updates_detail_and_user_counters(behavior_records):
    db, user, stats, image, *_ = behavior_records
    before_image = image.view_count
    before_user = stats.view_count

    result = await record_view(
        db,
        image_id=image.id,
        user_id=user.id,
        visitor_id="visitor-test",
        ip_address="127.0.0.1",
        user_agent="pytest",
    )

    await db.refresh(image)
    await db.refresh(stats)
    record_count = await db.scalar(
        select(func.count()).select_from(ImageViewRecord).where(
            ImageViewRecord.user_id == user.id,
            ImageViewRecord.image_id == image.id,
        )
    )
    assert result == {"image_id": image.id, "view_count": before_image + 1}
    assert image.view_count == before_image + 1
    assert stats.view_count == before_user + 1
    assert record_count == 1


async def test_record_view_http_contract(authenticated_client, behavior_records):
    _, _, _, image, *_ = behavior_records
    response = await authenticated_client.post(
        f"/api/images/{image.id}/view",
        json={"visitor_id": "browser-visitor"},
    )

    assert response.status_code == 200
    assert response.json()["code"] == 200
    assert response.json()["data"]["image_id"] == image.id
    assert isinstance(response.json()["data"]["view_count"], int)
