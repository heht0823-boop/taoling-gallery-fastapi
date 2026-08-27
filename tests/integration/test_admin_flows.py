import shutil
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image as PILImage
from sqlalchemy import select

from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_access_token
from app.main import app
from app.models.image import ImageTag, Tag
from app.models.message import UserMessage
from app.models.user import User, UserStat


def _png_bytes() -> bytes:
    buffer = BytesIO()
    PILImage.new("RGB", (640, 480), color=(72, 128, 184)).save(buffer, "PNG")
    return buffer.getvalue()


@pytest.fixture
def admin_upload_root():
    tests_root = Path(__file__).resolve().parents[2] / "uploads" / "tests"
    root = tests_root / uuid4().hex
    root.mkdir(parents=True)
    try:
        yield root
    finally:
        assert root.parent == tests_root
        shutil.rmtree(root, ignore_errors=True)


@pytest.fixture
async def admin_records(behavior_records):
    db, user, stats, public_image, private_image, related_image, matching_tag = (
        behavior_records
    )
    suffix = uuid4().hex[:10]
    admin = User(
        username=f"admin-{suffix}",
        email=f"admin-{suffix}@example.test",
        password_hash="test-only",
        role="admin",
        status="normal",
    )
    db.add(admin)
    await db.flush()
    db.add(UserStat(user_id=admin.id))
    await db.commit()
    return (
        db,
        admin,
        user,
        stats,
        public_image,
        private_image,
        related_image,
        matching_tag,
    )


@pytest.fixture
async def admin_client(admin_records):
    db, admin, *_ = admin_records

    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            client.cookies.set(
                settings.auth_cookie_name,
                create_access_token(admin.id, admin.role),
            )
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)


async def test_admin_routes_enforce_role(authenticated_client):
    response = await authenticated_client.get("/api/admin/dashboard/stats")

    assert response.status_code == 403
    assert response.json()["code"] == 403


async def test_admin_dashboard_and_taxonomy_crud(
    admin_client,
    admin_records,
):
    *_, public_image, _, _, matching_tag = admin_records
    suffix = uuid4().hex[:8]
    stats = await admin_client.get("/api/admin/dashboard/stats")
    categories = await admin_client.get(
        "/api/admin/categories",
        params={"page": 1, "pageSize": 100},
    )
    blocked_category = await admin_client.delete(
        f"/api/admin/categories/{public_image.category_id}"
    )
    blocked_tag = await admin_client.delete(f"/api/admin/tags/{matching_tag.id}")

    created_category = await admin_client.post(
        "/api/admin/categories",
        json={"name": f"管理分类-{suffix}", "sort_order": 50},
    )
    category_id = created_category.json()["data"]["id"]
    updated_category = await admin_client.patch(
        f"/api/admin/categories/{category_id}",
        json={"sort_order": 60, "status": "disabled"},
    )
    removed_category = await admin_client.delete(
        f"/api/admin/categories/{category_id}"
    )

    created_tag = await admin_client.post(
        "/api/admin/tags",
        json={"name": f"管理标签-{suffix}", "color": "#abcdef"},
    )
    tag_id = created_tag.json()["data"]["id"]
    updated_tag = await admin_client.put(
        f"/api/admin/tags/{tag_id}",
        json={"color": "#123456"},
    )
    removed_tag = await admin_client.delete(f"/api/admin/tags/{tag_id}")
    logs = await admin_client.get(
        "/api/admin/logs",
        params={"page": 1, "pageSize": 100},
    )

    assert stats.status_code == 200
    assert {
        "image_count",
        "user_count",
        "total_view_count",
        "total_download_count",
        "total_favorite_count",
        "ai_conversation_count",
    } == set(stats.json()["data"])
    assert categories.json()["data"]["pagination"]["total"] >= 1
    assert blocked_category.status_code == 400
    assert blocked_tag.status_code == 400
    assert created_category.status_code == 201
    assert updated_category.json()["data"]["sort_order"] == 60
    assert removed_category.json()["data"] == {}
    assert created_tag.status_code == 201
    assert updated_tag.json()["data"]["color"] == "#123456"
    assert removed_tag.json()["data"] == {}
    assert logs.json()["data"]["pagination"]["total"] >= 6


async def test_admin_image_crud_preserves_complete_tag_context(
    admin_client,
    admin_records,
):
    db, _, _, _, public_image, _, _, matching_tag = admin_records
    suffix = uuid4().hex[:8]
    second_tag = Tag(
        name=f"管理图片完整标签-{suffix}",
        color="#654321",
        usage_count=0,
        status="normal",
    )
    db.add(second_tag)
    await db.commit()

    created = await admin_client.post(
        "/api/admin/images",
        json={
            "title": f"管理图片-{suffix}",
            "image_url": f"https://example.test/admin-{suffix}.jpg",
            "categoryId": public_image.category_id,
            "status": "draft",
            "tagIds": [matching_tag.id, second_tag.id],
        },
    )
    image_id = created.json()["data"]["id"]
    listed = await admin_client.get(
        "/api/admin/images",
        params={"tag_id": matching_tag.id, "keyword": suffix},
    )
    detail = await admin_client.get(f"/api/admin/images/{image_id}")
    updated = await admin_client.put(
        f"/api/admin/images/{image_id}",
        json={"title": f"已更新-{suffix}", "tag_ids": [second_tag.id]},
    )
    published = await admin_client.patch(
        f"/api/admin/images/{image_id}/status",
        json={"status": "public"},
    )
    deleted = await admin_client.delete(f"/api/admin/images/{image_id}")
    deleted_list = await admin_client.get(
        "/api/admin/images",
        params={"status": "deleted", "keyword": suffix},
    )
    restored = await admin_client.patch(
        f"/api/admin/images/{image_id}/restore",
        json={"status": "draft"},
    )

    await db.refresh(matching_tag)
    await db.refresh(second_tag)
    links = set(
        (
            await db.scalars(
                select(ImageTag.tag_id).where(ImageTag.image_id == image_id)
            )
        ).all()
    )

    assert created.status_code == 201
    assert set(listed.json()["data"]["list"][0]["tag_ids"]) == {
        matching_tag.id,
        second_tag.id,
    }
    assert set(detail.json()["data"]["tag_ids"]) == {
        matching_tag.id,
        second_tag.id,
    }
    assert updated.json()["data"]["title"] == f"已更新-{suffix}"
    assert links == {second_tag.id}
    assert published.json()["data"]["status"] == "public"
    assert deleted.json()["data"] == {}
    assert deleted_list.json()["data"]["pagination"]["total"] == 1
    assert restored.json()["data"]["status"] == "draft"
    assert restored.json()["data"]["deleted_at"] is None


async def test_admin_users_and_messages(admin_client, admin_records):
    db, admin, user, *_ = admin_records
    root = UserMessage(
        user_id=user.id,
        content="管理员处理留言",
        check_status="success",
    )
    db.add(root)
    await db.commit()

    users = await admin_client.get(
        "/api/admin/users",
        params={"keyword": user.username},
    )
    detail = await admin_client.get(f"/api/admin/users/{user.id}")
    disabled = await admin_client.patch(
        f"/api/admin/users/{user.id}/status",
        json={"status": "disabled"},
    )
    self_disabled = await admin_client.patch(
        f"/api/admin/users/{admin.id}/status",
        json={"status": "disabled"},
    )
    messages = await admin_client.get(
        "/api/admin/messages",
        params={"keyword": "管理员处理留言"},
    )
    message_detail = await admin_client.get(f"/api/admin/messages/{root.id}")
    reply = await admin_client.post(
        f"/api/admin/messages/{root.id}/replies",
        json={"content": "管理员公开回复"},
    )
    blocked = await admin_client.delete(f"/api/admin/messages/{root.id}")

    assert users.json()["data"]["pagination"]["total"] == 1
    assert detail.json()["data"]["id"] == user.id
    assert "stats" in detail.json()["data"]
    assert disabled.json()["data"]["status"] == "disabled"
    assert self_disabled.status_code == 400
    assert messages.json()["data"]["list"][0]["id"] == root.id
    assert message_detail.json()["data"]["replies"] == []
    assert reply.status_code == 201
    assert reply.json()["data"]["parent_id"] == root.id
    assert blocked.json()["data"]["check_status"] == "block"


async def test_admin_image_upload_returns_frontend_fields(
    admin_client,
    monkeypatch,
    admin_upload_root,
):
    monkeypatch.setattr(
        "app.services.admin.image_service.settings.upload_root",
        str(admin_upload_root),
    )
    response = await admin_client.post(
        "/api/admin/files/images",
        files={"file": ("pixel.png", _png_bytes(), "image/png")},
    )
    data = response.json()["data"]

    assert response.status_code == 201
    assert data["image_url"].endswith(".png")
    assert data["thumbnail_url"]
    assert data["thumbnail_srcset"]
    assert data["processor_enabled"] is True
    assert len(list(admin_upload_root.glob("image-*.png"))) == 1
    assert len(list((admin_upload_root / "variants").glob("*.webp"))) == 2
