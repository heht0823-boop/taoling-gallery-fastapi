"""桃灵助手可调用的真实图库工具。

工具只查询公开且未删除的图片，推荐结果复用公开图库序列化字段，并额外提供
``detail_url``。搜索、热门、最新以及批量收藏的结果结构与 Node 服务保持一致。
"""

import re

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.behavior import Favorite
from app.models.image import Category, Image, ImageTag, Tag
from app.models.user import User
from app.services import favorite_service, image_service

IMAGE_TOOL_NAMES = {"search_images", "get_hot_images", "get_latest_images"}


def deterministic_calls(message: str) -> list[dict]:
    """在模型规划不可用时，从中文意图稳定选择图库工具。"""

    if re.search(r"收藏|加入.*收藏|帮我收", message, re.I):
        return [{"name": "add_favorites", "arguments": {}}]
    if re.search(r"热门|最多人看|热度|爆款", message, re.I):
        return [{"name": "get_hot_images", "arguments": {"limit": 6}}]
    if re.search(r"最新|刚发布|新图|最近发布", message, re.I):
        return [{"name": "get_latest_images", "arguments": {"limit": 6}}]
    if re.search(r"找|搜索|查找|推荐|看看|图库|图片|图像|壁纸|头像|风格|标签|分类", message, re.I):
        return [{"name": "search_images", "arguments": {"keyword": message, "limit": 6}}]
    return []


def search_tokens(value: str) -> list[str]:
    """移除常见口语停用词，提取适合 LIKE 查询的搜索片段。"""

    cleaned = re.sub(
        r"帮我|给我|麻烦|请|想要|看看|看一下|找找|查找|搜索|推荐|图片|图像|"
        r"图库|作品|有没有|一下|一些|什么|相关|最新|热门|发布|的|了|呢|吗|吧|呀|啊",
        " ",
        value,
        flags=re.I,
    )
    parts = re.split(r"[，。！？、,.!?;；:：()\[\]{}\s]+", cleaned)
    return list(dict.fromkeys(item.strip() for item in parts if len(item.strip()) >= 2))[:8]


def normalize_image_ids(value: object, limit: int = 12) -> list[int]:
    """把模型或客户端给出的图片 ID 转为有序、去重的正整数数组。"""

    if not isinstance(value, list):
        return []
    result: list[int] = []
    for item in value:
        try:
            image_id = int(item)
        except (TypeError, ValueError):
            continue
        if image_id > 0 and image_id not in result:
            result.append(image_id)
    return result[:limit]


async def find_images(
    db: AsyncSession,
    *,
    user_id: int,
    keyword: str = "",
    tags: list[str] | None = None,
    category: str = "",
    sort: str = "weight",
    limit: int = 6,
) -> list[dict]:
    """按关键词/标签/分类查图库，并批量装配分类、标签和收藏状态。"""

    # 模型 function calling 的参数仍属于外部输入：即使 JSON Schema 声明了类型，
    # 也要在进入 SQL 构造前转换，避免非数字 limit 或不可哈希 sort 触发 500。
    clean_keyword = str(keyword or "").strip()
    clean_category = str(category or "").strip()
    clean_sort = str(sort or "weight")
    try:
        clean_limit = int(limit or 6)
    except (TypeError, ValueError):
        clean_limit = 6
    raw_tags = tags if isinstance(tags, list) else []
    clean_tags = list(
        dict.fromkeys(str(item).strip() for item in raw_tags if str(item).strip())
    )[:8]
    tokens = list(
        dict.fromkeys(
            [
                *search_tokens(clean_keyword),
                *clean_tags,
                *([clean_category] if clean_category else []),
            ]
        )
    )
    conditions = [Image.status == "public", Image.deleted_at.is_(None)]
    if tokens:
        matches = []
        for token in tokens[:10]:
            value = f"%{token}%"
            tag_match = (
                select(ImageTag.image_id)
                .join(Tag, Tag.id == ImageTag.tag_id)
                .where(Tag.name.like(value), Tag.deleted_at.is_(None))
            )
            matches.extend(
                [
                    Image.title.like(value),
                    Image.description.like(value),
                    Image.id.in_(tag_match),
                ]
            )
        conditions.append(or_(*matches))
    if clean_category:
        category_id = await db.scalar(
            select(Category.id).where(
                Category.name.like(f"%{clean_category}%"),
                Category.status == "normal",
                Category.deleted_at.is_(None),
            )
        )
        if category_id:
            conditions.append(Image.category_id == category_id)
    if clean_tags:
        tagged_ids = (
            select(ImageTag.image_id)
            .join(Tag, Tag.id == ImageTag.tag_id)
            .where(Tag.name.in_(clean_tags), Tag.deleted_at.is_(None))
        )
        conditions.append(Image.id.in_(tagged_ids))
    order_map = {
        "latest": (Image.created_at.desc(),),
        "hot": (Image.view_count.desc(), Image.created_at.desc()),
        "downloads": (Image.download_count.desc(), Image.created_at.desc()),
        "favorites": (Image.favorite_count.desc(), Image.created_at.desc()),
        "weight": (Image.display_weight.desc(), Image.created_at.desc()),
    }
    rows = list(
        (
            await db.scalars(
                select(Image)
                .where(*conditions)
                .order_by(*order_map.get(clean_sort, order_map["weight"]))
                .limit(min(max(clean_limit, 1), 12))
            )
        ).all()
    )
    category_map, tags_by_image, favorite_ids = await image_service._load_image_context(
        db,
        rows,
        current_user_id=user_id,
    )
    result = []
    for image in rows:
        item = image_service.serialize_image(
            image,
            category=category_map.get(image.category_id),
            tags=tags_by_image.get(image.id, []),
            is_favorited=image.id in favorite_ids,
        )
        item["detail_url"] = f"/images/{image.id}"
        result.append(item)
    return result


async def _last_recommended_ids(
    db: AsyncSession,
    *,
    conversation_id: int,
    user_id: int,
) -> list[int]:
    """读取会话最近一条助手消息的推荐图片，供“收藏这些”省略 ID 时使用。"""

    from app.models.ai import AiMessage

    row = await db.scalar(
        select(AiMessage)
        .where(
            AiMessage.conversation_id == conversation_id,
            AiMessage.user_id == user_id,
            AiMessage.role == "assistant",
            AiMessage.deleted_at.is_(None),
        )
        .order_by(AiMessage.created_at.desc(), AiMessage.id.desc())
    )
    return normalize_image_ids(row.recommended_image_ids if row else [])


async def execute_calls(
    db: AsyncSession,
    *,
    user: User,
    conversation_id: int,
    calls: list[dict],
    ip_address: str | None,
) -> dict:
    """串行执行工具并去重推荐图；收藏复用现有幂等计数事务。"""

    images: list[dict] = []
    tool_results: list[dict] = []
    favorite_result: dict | None = None
    for call in calls:
        name = call.get("name")
        arguments = call.get("arguments") or {}
        if name in IMAGE_TOOL_NAMES:
            sort = {
                "get_hot_images": "hot",
                "get_latest_images": "latest",
            }.get(name, arguments.get("sort") or "weight")
            result = await find_images(
                db,
                user_id=user.id,
                keyword=arguments.get("keyword") or "",
                tags=arguments.get("tags") or [],
                category=arguments.get("category") or "",
                sort=sort,
                limit=arguments.get("limit") or 6,
            )
            images.extend(result)
            tool_results.append({"tool": name, "result": result})
        elif name == "add_favorites":
            ids = normalize_image_ids(arguments.get("image_ids"))
            if not ids:
                ids = await _last_recommended_ids(
                    db,
                    conversation_id=conversation_id,
                    user_id=user.id,
                )
            existing_ids = set(
                (
                    await db.scalars(
                        select(Favorite.image_id).where(
                            Favorite.user_id == user.id,
                            Favorite.image_id.in_(ids or [-1]),
                        )
                    )
                ).all()
            )
            added: list[int] = []
            for image_id in ids:
                if image_id in existing_ids:
                    continue
                try:
                    await favorite_service.add_favorite(
                        db,
                        user=user,
                        image_id=image_id,
                        ip_address=ip_address,
                    )
                    added.append(image_id)
                except AppError as exc:
                    # 与旧 Sequelize 实现一致：模型给出不存在的图片 ID 时忽略；
                    # 重复收藏也只进入 existed，不让整轮 AI 回复失败。
                    if exc.status_code not in {404, 409}:
                        raise
            favorite_result = {
                "added": added,
                "existed": [item for item in ids if item in existing_ids],
            }
            tool_results.append({"tool": name, "result": favorite_result})
    unique_images = list({int(item["id"]): item for item in images}.values())[:12]
    return {
        "images": unique_images,
        "tool_results": tool_results,
        "favorite_result": favorite_result,
    }
