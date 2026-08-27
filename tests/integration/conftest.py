from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import engine
from app.models.image import Category, Image, ImageTag, Tag
from app.models.user import User, UserStat


@pytest.fixture
async def gallery_records():
    async with engine.connect() as connection:
        transaction = await connection.begin()
        db = AsyncSession(
            bind=connection,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        suffix = uuid4().hex[:10]
        category = Category(name=f"测试分类-{suffix}", sort_order=999, status="normal")
        matching_tag = Tag(
            name=f"关键标签-{suffix}",
            color="#112233",
            usage_count=2,
            status="normal",
        )
        second_tag = Tag(
            name=f"完整标签-{suffix}",
            color="#445566",
            usage_count=1,
            status="normal",
        )
        db.add_all([category, matching_tag, second_tag])
        await db.flush()

        public_image = Image(
            title=f"公开图片-{suffix}",
            description="用于公开图库集成测试",
            image_url=f"https://example.test/{suffix}.jpg",
            category_id=category.id,
            aspect_ratio="1:1",
            status="public",
            display_weight=10,
        )
        private_image = Image(
            title=f"隐藏图片-{suffix}",
            image_url=f"https://example.test/private-{suffix}.jpg",
            category_id=category.id,
            status="private",
        )
        related_image = Image(
            title=f"相关推荐-{suffix}",
            image_url=f"https://example.test/related-{suffix}.jpg",
            category_id=category.id,
            status="public",
            display_weight=5,
        )
        db.add_all([public_image, private_image, related_image])
        await db.flush()
        db.add_all(
            [
                ImageTag(image_id=public_image.id, tag_id=matching_tag.id),
                ImageTag(image_id=public_image.id, tag_id=second_tag.id),
                ImageTag(image_id=private_image.id, tag_id=matching_tag.id),
            ]
        )
        await db.flush()

        try:
            yield db, public_image, private_image, related_image, matching_tag
        finally:
            await db.close()
            await transaction.rollback()


@pytest.fixture
async def behavior_records(gallery_records):
    db, public_image, private_image, related_image, matching_tag = gallery_records
    suffix = uuid4().hex[:10]
    user = User(
        username=f"behavior-{suffix}",
        email=f"behavior-{suffix}@example.test",
        password_hash="test-only",
        role="user",
        status="normal",
    )
    db.add(user)
    await db.flush()
    stats = UserStat(user_id=user.id)
    db.add(stats)
    await db.flush()
    return db, user, stats, public_image, private_image, related_image, matching_tag
