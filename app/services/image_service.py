from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.image import Category, Image, Tag
from app.utils.image_url import image_thumbnail_url, normalize_image_url


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
