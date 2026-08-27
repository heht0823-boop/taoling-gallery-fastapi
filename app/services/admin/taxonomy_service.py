"""管理后台分类与标签 CRUD、引用保护和审计事务。

分类/标签采用软删除；仍被有效图片引用时拒绝删除，避免公开图库出现孤立关联。
数据库唯一约束作为并发兜底，冲突统一转换为 409。
"""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import bad_request, conflict, not_found
from app.models.image import Category, Image, ImageTag, Tag
from app.models.user import User
from app.services.log_service import write_log
from app.utils.pagination import normalize_pagination, pagination_payload


def _serialize_category(category: Category, *, image_count: int = 0) -> dict:
    """输出分类及有效图片引用数。"""

    return {
        "id": category.id,
        "name": category.name,
        "sort_order": category.sort_order,
        "status": category.status,
        "image_count": image_count,
        "created_at": category.created_at,
        "updated_at": category.updated_at,
        "deleted_at": category.deleted_at,
    }


def _serialize_tag(tag: Tag) -> dict:
    """输出标签及持久化的引用计数。"""

    return {
        "id": tag.id,
        "name": tag.name,
        "color": tag.color,
        "usage_count": tag.usage_count,
        "status": tag.status,
        "created_at": tag.created_at,
        "updated_at": tag.updated_at,
        "deleted_at": tag.deleted_at,
    }


async def list_categories(
    db: AsyncSession,
    *,
    page: int,
    page_size: int,
    keyword: str | None,
    status: str | None,
) -> dict:
    """分页查询未删除分类，并在一条聚合子查询中统计图片数。"""

    page, page_size, offset = normalize_pagination(page, page_size)
    conditions = [Category.deleted_at.is_(None)]
    if keyword and (value := keyword.strip()):
        conditions.append(Category.name.like(f"%{value}%"))
    if status:
        conditions.append(Category.status == status)

    image_counts = (
        select(Image.category_id, func.count(Image.id).label("image_count"))
        .where(Image.deleted_at.is_(None), Image.status != "deleted")
        .group_by(Image.category_id)
        .subquery()
    )
    total = await db.scalar(select(func.count()).select_from(Category).where(*conditions)) or 0
    rows = (
        await db.execute(
            select(
                Category,
                func.coalesce(image_counts.c.image_count, 0),
            )
            .outerjoin(image_counts, image_counts.c.category_id == Category.id)
            .where(*conditions)
            .order_by(Category.sort_order.desc(), Category.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
    ).all()
    return {
        "list": [_serialize_category(category, image_count=image_count) for category, image_count in rows],
        "pagination": pagination_payload(
            page=page,
            page_size=page_size,
            total=total,
        ),
    }


async def _active_category(db: AsyncSession, category_id: int) -> Category:
    """读取有效分类，隐藏已软删除记录。"""

    category = await db.scalar(
        select(Category).where(
            Category.id == category_id,
            Category.deleted_at.is_(None),
        )
    )
    if not category:
        raise not_found("分类不存在")
    return category


async def create_category(
    db: AsyncSession,
    *,
    admin: User,
    name: str,
    sort_order: int,
    status: str,
    ip_address: str | None,
) -> dict:
    """创建唯一分类并记录管理员操作；并发重名统一返回 409。"""

    name = name.strip()
    if not name:
        raise bad_request("分类名称不能为空")
    duplicate = await db.scalar(
        select(Category.id).where(
            Category.name == name,
            Category.deleted_at.is_(None),
        )
    )
    if duplicate:
        raise conflict("分类名称已存在")
    category = Category(name=name, sort_order=sort_order, status=status)
    db.add(category)
    await db.flush()
    await write_log(
        db,
        actor=admin,
        action_type="CATEGORY_CREATE",
        target_type="category",
        target_id=category.id,
        title="新增分类",
        content=f"{admin.username} 新增分类 {category.name}",
        ip_address=ip_address,
    )
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise conflict("分类名称已存在") from exc
    await db.refresh(category)
    return _serialize_category(category)


async def update_category(
    db: AsyncSession,
    *,
    admin: User,
    category_id: int,
    updates: dict,
    ip_address: str | None,
) -> dict:
    """局部更新分类并返回更新后的有效图片引用数。"""

    category = await _active_category(db, category_id)
    if updates.get("name") is not None:
        name = str(updates["name"]).strip()
        if not name:
            raise bad_request("分类名称不能为空")
        duplicate = await db.scalar(
            select(Category.id).where(
                Category.id != category.id,
                Category.name == name,
                Category.deleted_at.is_(None),
            )
        )
        if duplicate:
            raise conflict("分类名称已存在")
        category.name = name
    if updates.get("sort_order") is not None:
        category.sort_order = updates["sort_order"]
    if updates.get("status") is not None:
        category.status = updates["status"]
    await write_log(
        db,
        actor=admin,
        action_type="CATEGORY_UPDATE",
        target_type="category",
        target_id=category.id,
        title="编辑分类",
        content=f"{admin.username} 编辑分类 {category.name}",
        ip_address=ip_address,
    )
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise conflict("分类名称已存在") from exc
    await db.refresh(category)
    image_count = (
        await db.scalar(
            select(func.count())
            .select_from(Image)
            .where(
                Image.category_id == category.id,
                Image.deleted_at.is_(None),
                Image.status != "deleted",
            )
        )
        or 0
    )
    return _serialize_category(category, image_count=image_count)


async def delete_category(
    db: AsyncSession,
    *,
    admin: User,
    category_id: int,
    ip_address: str | None,
) -> dict:
    """无有效图片引用时软删除分类，否则返回可操作的 400 提示。"""

    category = await _active_category(db, category_id)
    image_count = (
        await db.scalar(
            select(func.count())
            .select_from(Image)
            .where(
                Image.category_id == category.id,
                Image.deleted_at.is_(None),
                Image.status != "deleted",
            )
        )
        or 0
    )
    if image_count:
        raise bad_request("该分类下仍有图片，请先转移图片后再删除")
    category.deleted_at = datetime.now()
    category.status = "disabled"
    await write_log(
        db,
        actor=admin,
        action_type="CATEGORY_DELETE",
        target_type="category",
        target_id=category.id,
        title="删除分类",
        content=f"{admin.username} 删除分类 {category.name}",
        ip_address=ip_address,
    )
    await db.commit()
    return {}


async def list_tags(
    db: AsyncSession,
    *,
    page: int,
    page_size: int,
    keyword: str | None,
    status: str | None,
) -> dict:
    """分页查询未删除标签，默认按引用热度和创建时间排序。"""

    page, page_size, offset = normalize_pagination(page, page_size)
    conditions = [Tag.deleted_at.is_(None)]
    if keyword and (value := keyword.strip()):
        conditions.append(Tag.name.like(f"%{value}%"))
    if status:
        conditions.append(Tag.status == status)
    total = await db.scalar(select(func.count()).select_from(Tag).where(*conditions)) or 0
    tags = list(
        (
            await db.scalars(
                select(Tag)
                .where(*conditions)
                .order_by(Tag.usage_count.desc(), Tag.created_at.desc())
                .offset(offset)
                .limit(page_size)
            )
        ).all()
    )
    return {
        "list": [_serialize_tag(tag) for tag in tags],
        "pagination": pagination_payload(
            page=page,
            page_size=page_size,
            total=total,
        ),
    }


async def _active_tag(db: AsyncSession, tag_id: int) -> Tag:
    """读取有效标签，隐藏已软删除记录。"""

    tag = await db.scalar(select(Tag).where(Tag.id == tag_id, Tag.deleted_at.is_(None)))
    if not tag:
        raise not_found("标签不存在")
    return tag


async def create_tag(
    db: AsyncSession,
    *,
    admin: User,
    name: str,
    color: str | None,
    status: str,
    ip_address: str | None,
) -> dict:
    """创建唯一标签并记录管理员审计日志。"""

    name = name.strip()
    if not name:
        raise bad_request("标签名称不能为空")
    duplicate = await db.scalar(select(Tag.id).where(Tag.name == name, Tag.deleted_at.is_(None)))
    if duplicate:
        raise conflict("标签名称已存在")
    tag = Tag(name=name, color=color or None, status=status)
    db.add(tag)
    await db.flush()
    await write_log(
        db,
        actor=admin,
        action_type="TAG_CREATE",
        target_type="tag",
        target_id=tag.id,
        title="新增标签",
        content=f"{admin.username} 新增标签 {tag.name}",
        ip_address=ip_address,
    )
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise conflict("标签名称已存在") from exc
    await db.refresh(tag)
    return _serialize_tag(tag)


async def update_tag(
    db: AsyncSession,
    *,
    admin: User,
    tag_id: int,
    updates: dict,
    ip_address: str | None,
) -> dict:
    """局部更新标签名称、颜色或状态，引用计数保持不变。"""

    tag = await _active_tag(db, tag_id)
    if updates.get("name") is not None:
        name = str(updates["name"]).strip()
        if not name:
            raise bad_request("标签名称不能为空")
        duplicate = await db.scalar(
            select(Tag.id).where(
                Tag.id != tag.id,
                Tag.name == name,
                Tag.deleted_at.is_(None),
            )
        )
        if duplicate:
            raise conflict("标签名称已存在")
        tag.name = name
    if updates.get("color") is not None:
        tag.color = updates["color"] or None
    if updates.get("status") is not None:
        tag.status = updates["status"]
    await write_log(
        db,
        actor=admin,
        action_type="TAG_UPDATE",
        target_type="tag",
        target_id=tag.id,
        title="编辑标签",
        content=f"{admin.username} 编辑标签 {tag.name}",
        ip_address=ip_address,
    )
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise conflict("标签名称已存在") from exc
    await db.refresh(tag)
    return _serialize_tag(tag)


async def delete_tag(
    db: AsyncSession,
    *,
    admin: User,
    tag_id: int,
    ip_address: str | None,
) -> dict:
    """仅允许软删除未被任何图片引用的标签。"""

    tag = await _active_tag(db, tag_id)
    used = await db.scalar(select(func.count()).select_from(ImageTag).where(ImageTag.tag_id == tag.id)) or 0
    if used:
        raise bad_request("该标签正在被图片使用，请先移除关联后再删除")
    tag.deleted_at = datetime.now()
    tag.status = "disabled"
    await write_log(
        db,
        actor=admin,
        action_type="TAG_DELETE",
        target_type="tag",
        target_id=tag.id,
        title="删除标签",
        content=f"{admin.username} 删除标签 {tag.name}",
        ip_address=ip_address,
    )
    await db.commit()
    return {}
