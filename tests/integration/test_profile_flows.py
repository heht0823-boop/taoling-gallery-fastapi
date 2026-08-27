import pytest

from app.core.exceptions import AppError
from app.core.security import hash_password, verify_password
from app.models.user import User
from app.services.profile_service import update_password, update_profile


async def test_profile_service_updates_fields_and_rejects_duplicates(
    behavior_records,
):
    db, user, *_ = behavior_records
    duplicate = User(
        username=f"duplicate-{user.id}",
        email=f"duplicate-{user.id}@example.test",
        password_hash="test-only",
        role="user",
        status="normal",
    )
    db.add(duplicate)
    await db.flush()

    result = await update_profile(
        db,
        user_id=user.id,
        updates={
            "username": f"updated-{user.id}",
            "email": "",
            "avatar_url": "/uploads/avatar-profile.jpg",
        },
        ip_address="127.0.0.1",
    )
    assert result["user"]["username"] == f"updated-{user.id}"
    assert result["user"]["email"] is None
    assert result["user"]["avatar_url"].endswith("/uploads/avatar-profile.jpg")
    assert result["user"]["avatar_thumbnail_url"].endswith(
        "/uploads/variants/avatar-profile-80w-q78.webp"
    )

    with pytest.raises(AppError) as exc_info:
        await update_profile(
            db,
            user_id=user.id,
            updates={"username": duplicate.username},
            ip_address="127.0.0.1",
        )
    assert exc_info.value.status_code == 409


async def test_password_service_verifies_old_password(behavior_records):
    db, user, *_ = behavior_records
    user.password_hash = hash_password("old-secret")
    await db.commit()

    with pytest.raises(AppError) as exc_info:
        await update_password(
            db,
            user_id=user.id,
            old_password="wrong-secret",
            new_password="new-secret",
            ip_address="127.0.0.1",
        )
    assert exc_info.value.status_code == 401

    await update_password(
        db,
        user_id=user.id,
        old_password="old-secret",
        new_password="new-secret",
        ip_address="127.0.0.1",
    )
    await db.refresh(user)
    assert verify_password("new-secret", user.password_hash) is True


async def test_profile_http_contract(authenticated_client, behavior_records):
    _, user, *_ = behavior_records
    summary = await authenticated_client.get("/api/user/profile/summary")
    updated = await authenticated_client.put(
        "/api/user/profile",
        json={"username": f"http-updated-{user.id}"},
    )
    empty = await authenticated_client.patch("/api/user/profile", json={})

    assert summary.status_code == 200
    assert summary.json()["data"]["user"]["id"] == user.id
    assert "stats" in summary.json()["data"]
    assert updated.json()["message"] == "资料修改成功"
    assert updated.json()["data"]["user"]["username"] == f"http-updated-{user.id}"
    assert empty.status_code == 400
