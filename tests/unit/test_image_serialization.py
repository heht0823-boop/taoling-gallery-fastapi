from datetime import datetime
from types import SimpleNamespace

from app.services.image_service import serialize_image
from app.utils.image_url import image_thumbnail_url, normalize_image_url


def make_image(**overrides):
    values = {
        "id": 7,
        "title": "测试图片",
        "description": None,
        "image_url": "/uploads/original.jpg",
        "thumbnail_url": None,
        "aspect_ratio": "1:1",
        "view_count": 3,
        "download_count": 2,
        "favorite_count": 1,
        "created_at": datetime(2026, 8, 27, 12, 0, 0),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_normalize_image_url_keeps_remote_and_expands_local(monkeypatch):
    monkeypatch.setattr("app.utils.image_url.settings.app_url", "http://api.test")
    assert normalize_image_url(" https://cdn.test/a.jpg/ ") == "https://cdn.test/a.jpg"
    assert normalize_image_url("/uploads/a.jpg") == "http://api.test/uploads/a.jpg"
    assert normalize_image_url(None) == ""


def test_thumbnail_uses_dynamic_endpoint_without_saved_variant(monkeypatch):
    monkeypatch.setattr("app.utils.image_url.settings.app_url", "http://api.test")
    image = make_image()
    assert image_thumbnail_url(image) == (
        "http://api.test/api/images/7/thumbnail?w=420&format=webp&q=78"
    )


def test_serialize_image_matches_gallery_contract(monkeypatch):
    monkeypatch.setattr("app.utils.image_url.settings.app_url", "http://api.test")
    category = SimpleNamespace(id=3, name="插画")
    tags = [SimpleNamespace(id=5, name="治愈", color="#ff8bb3")]

    payload = serialize_image(
        make_image(),
        category=category,
        tags=tags,
        is_favorited=True,
    )

    assert set(payload) == {
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
    assert payload["image_url"] == "http://api.test/uploads/original.jpg"
    assert payload["category"] == {"id": 3, "name": "插画"}
    assert payload["tags"] == [{"id": 5, "name": "治愈", "color": "#ff8bb3"}]
    assert payload["is_favorited"] is True
