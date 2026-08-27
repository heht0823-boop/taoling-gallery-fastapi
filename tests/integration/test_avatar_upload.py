import shutil
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest
from PIL import Image as PILImage


def _png_bytes() -> bytes:
    buffer = BytesIO()
    PILImage.new("RGB", (240, 180), color=(54, 112, 168)).save(buffer, "PNG")
    return buffer.getvalue()


@pytest.fixture
def avatar_upload_root():
    tests_root = Path(__file__).resolve().parents[2] / "uploads" / "tests"
    root = tests_root / uuid4().hex
    root.mkdir(parents=True)
    try:
        yield root
    finally:
        assert root.parent == tests_root
        shutil.rmtree(root, ignore_errors=True)


async def test_avatar_upload_generates_variants_and_updates_profile(
    authenticated_client,
    behavior_records,
    monkeypatch,
    avatar_upload_root,
):
    _, user, *_ = behavior_records
    upload_root = avatar_upload_root
    monkeypatch.setattr(
        "app.services.avatar_service.settings.upload_root",
        str(upload_root),
    )

    response = await authenticated_client.post(
        "/api/user/profile/avatar",
        files={"file": ("avatar.png", _png_bytes(), "image/png")},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["user"]["id"] == user.id
    assert data["user"]["avatar_url"] == data["avatar_upload"]["avatar_url"]
    assert data["avatar_upload"]["processor_enabled"] is True
    assert " 1x, " in data["avatar_upload"]["avatar_srcset"]
    assert len(list(upload_root.glob("avatar-*.png"))) == 1
    assert len(list((upload_root / "variants").glob("*.webp"))) == 2


async def test_avatar_upload_rejects_invalid_file(
    authenticated_client,
    monkeypatch,
    avatar_upload_root,
):
    monkeypatch.setattr(
        "app.services.avatar_service.settings.upload_root",
        str(avatar_upload_root),
    )
    response = await authenticated_client.post(
        "/api/user/profile/avatar",
        files={"file": ("avatar.png", b"not-an-image", "image/png")},
    )
    assert response.status_code == 400
    assert response.json()["message"] == "头像文件不是有效图片"
