from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.behavior import Favorite
from app.models.image import Category, Image, ImageTag, Tag
from app.utils.image_url import image_thumbnail_url, normalize_image_url
from app.utils.pagination import normalize_pagination, pagination_payload


async def list_categories(db: AsyncSession) -> list[dict]:
    """
    获取正常状态的图片分类列表
    过滤已删除、禁用分类，按排序权重、创建时间倒序

    :param db: 异步数据库会话
    :return: 分类简易字典列表
    """
    stmt = (
        select(Category)
        .where(
            Category.status == "normal",
            Category.deleted_at.is_(None),
        )
        .order_by(Category.sort_order.desc(), Category.created_at.desc())
    )
    result = await db.execute(stmt)

    return [
        {
            "id": item.id,
            "name": item.name,
            "sort_order": item.sort_order,
        }
        for item in result.scalars().all()
    ]


async def list_tags(
    db: AsyncSession,
    *,
    keyword: str | None,
    limit: int,
) -> list[dict]:
    """
    获取标签列表，支持名称模糊搜索
    关键字仅对正常、未删除标签生效；limit做边界防护

    :param db: 异步数据库会话
    :param keyword: 搜索关键词，可为None，对标签名称模糊匹配
    :param limit: 查询条数上限
    :return: 标签字典列表
    """
    stmt = select(Tag).where(
        Tag.status == "normal",
        Tag.deleted_at.is_(None),
    )

    # 关键词模糊查询，先去除首尾空格；空字符串不追加where条件
    if keyword and (stripped := keyword.strip()):
        stmt = stmt.where(Tag.name.like(f"%{stripped}%"))

    # 按使用量降序，再创建时间降序
    stmt = stmt.order_by(Tag.usage_count.desc(), Tag.created_at.desc())
    # 边界保护：limit强制约束 [1,100]，防止数据库超大查询
    safe_limit = min(max(limit, 1), 100)
    stmt = stmt.limit(safe_limit)

    result = await db.execute(stmt)

    return [
        {
            "id": tag.id,
            "name": tag.name,
            "color": tag.color,
            "usage_count": tag.usage_count,
        }
        for tag in result.scalars().all()
    ]


def serialize_image(
    image: Image,
    *,
    category: Category | None,
    tags: list[Tag],
    is_favorited: bool,
) -> dict:
    """把图库 ORM 对象转换成 Vue 前端固定使用的 GalleryImage 字段。"""
    return {
        "id": image.id,
        "title": image.title,
        "description": image.description,
        "image_url": normalize_image_url(image.image_url),
        "thumbnail_url": image_thumbnail_url(image),
        "aspect_ratio": image.aspect_ratio,
        "category": {"id": category.id, "name": category.name} if category else None,
        "tags": [
            {"id": tag.id, "name": tag.name, "color": tag.color}
            for tag in tags
        ],
        "view_count": image.view_count,
        "download_count": image.download_count,
        "favorite_count": image.favorite_count,
        "is_favorited": is_favorited,
        "created_at": image.created_at,
    }


async def _load_image_context(
    db: AsyncSession,
    images: list[Image],
    *,
    current_user_id: int | None,
) -> tuple[dict[int, Category], dict[int, list[Tag]], set[int]]:
    """批量加载分类、完整标签和收藏状态，避免列表查询产生 N+1。"""
    image_ids = [image.id for image in images]
    category_ids = {image.category_id for image in images if image.category_id}

    category_map: dict[int, Category] = {}
    if category_ids:
        rows = await db.execute(select(Category).where(Category.id.in_(category_ids)))
        category_map = {category.id: category for category in rows.scalars().all()}

    tags_by_image: dict[int, list[Tag]] = {image.id: [] for image in images}
    if image_ids:
        rows = await db.execute(
            select(ImageTag.image_id, Tag)
            .join(Tag, Tag.id == ImageTag.tag_id)
            .where(
                ImageTag.image_id.in_(image_ids),
                Tag.status == "normal",
                Tag.deleted_at.is_(None),
            )
            .order_by(Tag.usage_count.desc(), Tag.created_at.desc())
        )
        for image_id, tag in rows.all():
            tags_by_image[image_id].append(tag)

    favorite_ids: set[int] = set()
    if current_user_id and image_ids:
        rows = await db.execute(
            select(Favorite.image_id).where(
                Favorite.user_id == current_user_id,
                Favorite.image_id.in_(image_ids),
            )
        )
        favorite_ids = set(rows.scalars().all())

    return category_map, tags_by_image, favorite_ids


async def list_images(
    db: AsyncSession,
    *,
    current_user_id: int | None,
    page: int,
    page_size: int,
    keyword: str | None,
    category_id: int | None,
    tag_ids: list[int] | None,
    aspect_ratio: str | None,
    sort: str | None,
) -> dict:
    """查询公开图库，兼容 Vue 当前使用的筛选、排序和分页契约。"""
    page, page_size, offset = normalize_pagination(page, page_size)
    conditions = [Image.status == "public", Image.deleted_at.is_(None)]

    if keyword and (search_term := keyword.strip()):
        value = f"%{search_term}%"
        tag_match = (
            select(ImageTag.image_id)
            .join(Tag, Tag.id == ImageTag.tag_id)
            .where(
                Tag.name.like(value),
                Tag.status == "normal",
                Tag.deleted_at.is_(None),
            )
        )
        conditions.append(
            or_(
                Image.title.like(value),
                Image.description.like(value),
                Image.id.in_(tag_match),
            )
        )

    if category_id is not None:
        conditions.append(Image.category_id == category_id)

    safe_tag_ids = sorted({tag_id for tag_id in tag_ids or [] if tag_id > 0})
    if safe_tag_ids:
        conditions.append(
            Image.id.in_(
                select(ImageTag.image_id).where(ImageTag.tag_id.in_(safe_tag_ids))
            )
        )

    if aspect_ratio and (ratio := aspect_ratio.strip()):
        conditions.append(Image.aspect_ratio == ratio)

    order_map = {
        "latest": (Image.created_at.desc(),),
        "hot": (Image.view_count.desc(), Image.created_at.desc()),
        "downloads": (Image.download_count.desc(), Image.created_at.desc()),
        "favorites": (Image.favorite_count.desc(), Image.created_at.desc()),
        "weight": (Image.display_weight.desc(), Image.created_at.desc()),
    }
    order_by = order_map.get(sort or "", order_map["weight"])

    total = await db.scalar(
        select(func.count()).select_from(
            select(Image.id).where(*conditions).subquery()
        )
    ) or 0
    rows = await db.execute(
        select(Image)
        .where(*conditions)
        .order_by(*order_by)
        .offset(offset)
        .limit(page_size)
    )
    images = list(rows.scalars().all())
    category_map, tags_by_image, favorite_ids = await _load_image_context(
        db,
        images,
        current_user_id=current_user_id,
    )

    return {
        "list": [
            serialize_image(
                image,
                category=category_map.get(image.category_id),
                tags=tags_by_image.get(image.id, []),
                is_favorited=image.id in favorite_ids,
            )
            for image in images
        ],
        "pagination": pagination_payload(
            page=page,
            page_size=page_size,
            total=total,
        ),
    }
