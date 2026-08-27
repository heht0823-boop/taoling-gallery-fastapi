import pytest
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.main import app

GALLERY_FIELDS = {
    "id",
    "title",
    "description",
    "image_url",
    "thumbnail_url",
    "aspect_ratio",
    "category",
    "tags",
    "view_count",
    "download_count",
    "favorite_count",
    "is_favorited",
    "created_at",
}


@pytest.fixture
async def gallery_client(gallery_records):
    db, *_ = gallery_records

    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)


async def test_public_gallery_http_contract(gallery_client, gallery_records):
    _, public_image, private_image, related_image, matching_tag = gallery_records
    response = await gallery_client.get(
        "/api/images",
        params={
            "page": 1,
            "pageSize": 12,
            "categoryId": public_image.category_id,
            "tag_ids": str(matching_tag.id),
            "keyword": matching_tag.name,
            "aspect_ratio": "1:1",
            "sort": "weight",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["data"]["pagination"]["total"] == 1
    assert set(body["data"]["list"][0]) == GALLERY_FIELDS
    assert body["data"]["list"][0]["id"] == public_image.id
    assert private_image.id not in {item["id"] for item in body["data"]["list"]}

    detail = await gallery_client.get(f"/api/images/{public_image.id}")
    assert detail.status_code == 200
    assert set(detail.json()["data"]) == GALLERY_FIELDS

    related = await gallery_client.get(f"/api/images/{public_image.id}/related?limit=20")
    related_ids = {item["id"] for item in related.json()["data"]}
    assert public_image.id not in related_ids
    assert related_image.id in related_ids


async def test_public_taxonomy_and_error_envelopes(gallery_client, gallery_records):
    _, _, private_image, _, matching_tag = gallery_records
    categories = await gallery_client.get("/api/categories")
    tags = await gallery_client.get("/api/tags", params={"keyword": matching_tag.name})
    hidden = await gallery_client.get(f"/api/images/{private_image.id}")
    invalid = await gallery_client.get("/api/images", params={"pageSize": 0})

    assert categories.status_code == 200
    assert any(item["id"] == matching_tag.id for item in tags.json()["data"])
    assert hidden.status_code == 404
    assert hidden.json()["code"] == 404
    assert invalid.status_code == 400
    assert invalid.json()["code"] == 400


async def test_thumbnail_redirect_has_long_cache_header(
    gallery_client,
    gallery_records,
    monkeypatch,
):
    _, public_image, *_ = gallery_records
    monkeypatch.setattr(
        "app.utils.image_url.settings.image_optimizer_query_template",
        "resize,w_{width},format_{format}",
    )
    response = await gallery_client.get(
        f"/api/images/{public_image.id}/thumbnail",
        params={"w": 320, "format": "webp", "q": 80},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["cache-control"] == "public, max-age=2592000, immutable"
