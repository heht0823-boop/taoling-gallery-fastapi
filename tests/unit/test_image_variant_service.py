from pathlib import Path

from app.services.image_variant_service import (
    local_upload_path_from_url,
    sanitize_format,
    sanitize_quality,
    sanitize_width,
)


def test_thumbnail_options_are_bounded():
    assert sanitize_width(1) == 32
    assert sanitize_width(3000) == 2000
    assert sanitize_quality(1) == 35
    assert sanitize_quality(100) == 95
    assert sanitize_format("jpeg") == "jpeg"
    assert sanitize_format("svg") == "webp"


def test_local_upload_path_rejects_directory_traversal(monkeypatch):
    upload_root = Path("C:/safe-uploads-test")
    monkeypatch.setattr(
        "app.services.image_variant_service.settings.upload_root",
        str(upload_root),
    )
    assert local_upload_path_from_url("http://api.test/uploads/image.jpg") == (
        upload_root / "image.jpg"
    ).resolve()
    assert local_upload_path_from_url("http://api.test/uploads/../secret.txt") is None
