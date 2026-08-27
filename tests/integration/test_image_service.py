import pytest

from app.core.exceptions import AppError
from app.services.image_service import (
    get_image_thumbnail,
    get_public_image,
    list_images,
    related_images,
)


async def test_list_images_filters_private_rows_and_keeps_complete_tags(gallery_records):
    db, public_image, private_image, _, matching_tag = gallery_records
    result = await list_images(
        db,
        current_user_id=None,
        page=1,
        page_size=12,
        keyword=matching_tag.name,
        category_id=public_image.category_id,
        tag_ids=[matching_tag.id],
        aspect_ratio="1:1",
        sort="weight",
    )

    assert result["pagination"]["total"] == 1
    assert result["pagination"]["totalPages"] == 1
    assert [item["id"] for item in result["list"]] == [public_image.id]
    assert private_image.id not in {item["id"] for item in result["list"]}
    tag_names = {tag["name"] for tag in result["list"][0]["tags"]}
    assert matching_tag.name in tag_names
    assert len(result["list"][0]["tags"]) == 2
    assert result["list"][0]["is_favorited"] is False


async def test_list_images_normalizes_page_size(gallery_records):
    db, *_ = gallery_records
    result = await list_images(
        db,
        current_user_id=None,
        page=0,
        page_size=999,
        keyword=None,
        category_id=None,
        tag_ids=None,
        aspect_ratio=None,
        sort="latest",
    )

    assert result["pagination"]["page"] == 1
    assert result["pagination"]["pageSize"] == 100


async def test_public_detail_and_related_share_gallery_contract(gallery_records):
    db, public_image, private_image, related_image, _ = gallery_records

    detail = await get_public_image(
        db,
        image_id=public_image.id,
        current_user_id=None,
    )
    related = await related_images(
        db,
        image_id=public_image.id,
        current_user_id=None,
        limit=100,
    )

    assert detail["id"] == public_image.id
    assert related_image.id in {item["id"] for item in related}
    assert public_image.id not in {item["id"] for item in related}
    assert all("category" in item and "tags" in item for item in related)

    with pytest.raises(AppError) as exc_info:
        await get_public_image(db, image_id=private_image.id, current_user_id=None)
    assert exc_info.value.status_code == 404


async def test_thumbnail_uses_configured_remote_optimizer(gallery_records, monkeypatch):
    db, public_image, *_ = gallery_records
    monkeypatch.setattr(
        "app.utils.image_url.settings.image_optimizer_query_template",
        "resize,w_{width},format_{format}",
    )

    result = await get_image_thumbnail(
        db,
        image_id=public_image.id,
        width=320,
        image_format="webp",
        quality=80,
    )

    assert result["type"] == "redirect"
    assert "resize,w_320,format_webp" in result["url"]
