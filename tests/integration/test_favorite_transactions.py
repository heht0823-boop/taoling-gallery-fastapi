import pytest
from sqlalchemy import func, select

from app.core.exceptions import AppError
from app.models.behavior import Favorite
from app.services.favorite_service import add_favorite, list_favorites, remove_favorite


async def test_favorite_service_updates_counts_and_is_idempotent(behavior_records):
    db, user, stats, image, *_ = behavior_records
    before_image = image.favorite_count
    before_user = stats.favorite_count

    added = await add_favorite(
        db,
        user=user,
        image_id=image.id,
        ip_address="127.0.0.1",
    )
    await db.refresh(image)
    await db.refresh(stats)
    assert added["is_favorited"] is True
    assert image.favorite_count == before_image + 1
    assert stats.favorite_count == before_user + 1

    with pytest.raises(AppError) as exc_info:
        await add_favorite(
            db,
            user=user,
            image_id=image.id,
            ip_address="127.0.0.1",
        )
    assert exc_info.value.status_code == 409

    page = await list_favorites(db, user_id=user.id, page=1, page_size=12)
    assert page["pagination"]["total"] == 1
    assert page["list"][0]["image"]["id"] == image.id

    removed = await remove_favorite(
        db,
        user=user,
        image_id=image.id,
        ip_address="127.0.0.1",
    )
    removed_again = await remove_favorite(
        db,
        user=user,
        image_id=image.id,
        ip_address="127.0.0.1",
    )
    await db.refresh(image)
    await db.refresh(stats)
    remaining = await db.scalar(
        select(func.count()).select_from(Favorite).where(Favorite.user_id == user.id)
    )
    assert removed["is_favorited"] is False
    assert removed_again["is_favorited"] is False
    assert image.favorite_count == before_image
    assert stats.favorite_count == before_user
    assert remaining == 0


async def test_favorite_http_and_compatibility_routes(
    authenticated_client,
    behavior_records,
):
    _, _, _, image, *_ = behavior_records
    added = await authenticated_client.post(f"/api/images/{image.id}/favorite")
    favorites = await authenticated_client.get(
        "/api/user/favorites",
        params={"page": 1, "pageSize": 12},
    )
    removed = await authenticated_client.delete(f"/api/images/{image.id}/favorite")
    alias_added = await authenticated_client.post(
        "/api/user/favorites",
        json={"imageId": image.id},
    )
    alias_removed = await authenticated_client.delete(
        f"/api/user/favorites/{image.id}"
    )

    assert added.status_code == 201
    assert favorites.status_code == 200
    assert favorites.json()["data"]["list"][0]["favorite_id"] > 0
    assert removed.json()["data"]["is_favorited"] is False
    assert alias_added.status_code == 201
    assert alias_removed.status_code == 200
