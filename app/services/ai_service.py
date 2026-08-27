"""桃灵助手的会话、消息、记忆和图库工具编排服务。

本模块对齐原 Express ``aiService`` 的业务契约，同时修复会话活跃时间不更新的
遗留问题。第三方模型不可用时，图库搜索、热门/最新推荐、收藏和本地兜底回复
仍可工作；会话归属、软删除、统计计数和审计日志均由服务层统一维护。
"""

import json
import logging
import re
from collections.abc import AsyncIterator
from datetime import datetime

from fastapi.encoders import jsonable_encoder
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import bad_request, not_found
from app.models.ai import AiConversation, AiMemory, AiMessage
from app.models.image import Category, Image, Tag
from app.models.user import User, UserStat
from app.services import ai_provider, ai_tools, image_service
from app.services.log_service import write_log

logger = logging.getLogger(__name__)

DEFAULT_TITLE = "新的对话"
FAVORITE_HINT = "需要把这些图片加入收藏吗？"
NO_IMAGE_REPLY = (
    "当前图库里暂时没有找到匹配的图片。你可以换个关键词再试试，"
    "或者去留言板留言，让管理员后续补充这类图片。"
)
IMAGE_GENERATION_REPLY = (
    "我目前不提供图片生成、绘图或修图能力。如果你需要某类图片，我可以帮你"
    "在桃灵图库里查找相近作品；也可以去留言板留言，让管理员后续制作或发布。"
)
IMAGE_TOOL_NAMES = {"search_images", "get_hot_images", "get_latest_images"}


def _is_image_generation_request(message: str) -> bool:
    """识别图片生成/绘制请求，避免向用户承诺当前不存在的生图能力。"""

    return bool(
        re.search(
            r"(生成|画|绘制|做一张|出一张|制作|create|generate|draw).{0,12}"
            r"(图片|图像|插画|壁纸|头像|海报|image|picture)",
            message,
            re.I,
        )
        or re.search(
            r"(图片|图像|插画|壁纸|头像|海报).{0,12}"
            r"(生成|绘制|制作|create|generate|draw)",
            message,
            re.I,
        )
    )


def _append_favorite_hint(reply: str, images: list[dict]) -> str:
    """推荐图片存在时追加收藏提示，并避免重复追加同一句文案。"""

    text = reply or ai_provider.FALLBACK_REPLY
    if not images or FAVORITE_HINT in text:
        return text
    return f"{text}\n\n{FAVORITE_HINT}"


def _has_image_tool_result(tool_results: list[dict]) -> bool:
    """判断本轮是否已经由受控图库工具给出了图片结果。"""

    return any(item.get("tool") in IMAGE_TOOL_NAMES for item in tool_results)


def _build_tool_messages(tool_results: list[dict]) -> list[dict]:
    """把真实工具结果转成模型上下文，禁止模型虚构不存在的图库内容。"""

    if not tool_results:
        return []
    payload = json.dumps(
        jsonable_encoder(tool_results),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return [
        {
            "role": "system",
            "content": f"后端图库工具结果如下，请基于真实结果回复用户：{payload}",
        }
    ]


async def _available_tags(db: AsyncSession) -> list[str]:
    """返回工具规划可使用的高频正常标签，最多读取 80 个。"""

    rows = await db.scalars(
        select(Tag.name)
        .where(Tag.status == "normal", Tag.deleted_at.is_(None))
        .order_by(Tag.usage_count.desc(), Tag.created_at.desc())
        .limit(80)
    )
    return list(rows.all())


async def _available_categories(db: AsyncSession) -> list[dict]:
    """返回工具规划可识别的正常分类名称和 ID。"""

    rows = await db.scalars(
        select(Category)
        .where(Category.status == "normal", Category.deleted_at.is_(None))
        .order_by(Category.sort_order.desc(), Category.created_at.desc())
        .limit(100)
    )
    return [{"id": item.id, "name": item.name} for item in rows.all()]


async def _memory_context(
    db: AsyncSession,
    *,
    user_id: int,
    conversation_id: int,
) -> dict:
    """装配当前会话短期记忆与跨会话长期偏好。"""

    short_memory = await db.scalar(
        select(AiMemory).where(
            AiMemory.user_id == user_id,
            AiMemory.conversation_id == conversation_id,
            AiMemory.memory_type == "short",
        )
    )
    long_memory = await db.scalar(
        select(AiMemory)
        .where(
            AiMemory.user_id == user_id,
            AiMemory.conversation_id.is_(None),
            AiMemory.memory_type == "long",
        )
        .order_by(AiMemory.updated_at.desc())
    )
    short_text = short_memory.content if short_memory else ""
    long_text = long_memory.content if long_memory else ""
    combined = "\n".join(
        item
        for item in (
            f"长期偏好：{long_text}" if long_text else "",
            f"当前会话摘要：{short_text}" if short_text else "",
        )
        if item
    )
    return {"short": short_text, "long": long_text, "text": combined}


async def _upsert_memory(
    db: AsyncSession,
    *,
    user_id: int,
    conversation_id: int,
    memory_type: str,
    content: str,
) -> None:
    """按用户、会话和记忆类型更新或新建一条记忆。"""

    if not content:
        return
    conversation_condition = (
        AiMemory.conversation_id.is_(None)
        if memory_type == "long"
        else AiMemory.conversation_id == conversation_id
    )
    current = await db.scalar(
        select(AiMemory).where(
            AiMemory.user_id == user_id,
            conversation_condition,
            AiMemory.memory_type == memory_type,
        )
    )
    if current:
        current.content = content
        return
    db.add(
        AiMemory(
            user_id=user_id,
            conversation_id=None if memory_type == "long" else conversation_id,
            memory_type=memory_type,
            content=content,
        )
    )


async def _conversation_history(
    db: AsyncSession,
    *,
    conversation_id: int,
    user_id: int,
) -> list[dict]:
    """读取最近十条未删除消息，并恢复成模型要求的正序上下文。"""

    rows = list(
        (
            await db.scalars(
                select(AiMessage)
                .where(
                    AiMessage.conversation_id == conversation_id,
                    AiMessage.user_id == user_id,
                    AiMessage.deleted_at.is_(None),
                )
                .order_by(AiMessage.created_at.desc(), AiMessage.id.desc())
                .limit(10)
            )
        ).all()
    )
    rows.reverse()
    return [{"role": row.role, "content": row.content} for row in rows]


def _resolve_search_arguments(
    *,
    raw_message: str,
    available_tags: list[str],
    categories: list[dict],
) -> dict:
    """从自然语言中补全模型可能遗漏的标签、分类和检索词。"""

    matched_tags = [tag for tag in available_tags if tag in raw_message][:8]
    category = next(
        (item["name"] for item in categories if item["name"] in raw_message),
        "",
    )
    return {
        "keyword": " ".join(ai_tools.search_tokens(raw_message)),
        "tags": matched_tags,
        "category": category,
    }


def _normalize_tool_calls(
    calls: list[dict],
    *,
    raw_message: str,
    available_tags: list[str],
    categories: list[dict],
) -> list[dict]:
    """清理工具参数，并为图片搜索调用补全可验证的本地意图。"""

    inferred = _resolve_search_arguments(
        raw_message=raw_message,
        available_tags=available_tags,
        categories=categories,
    )
    normalized: list[dict] = []
    for call in calls:
        name = call.get("name")
        arguments = call.get("arguments")
        arguments = arguments if isinstance(arguments, dict) else {}
        if name == "search_images":
            arguments = {
                **arguments,
                "keyword": arguments.get("keyword") or inferred["keyword"],
                "tags": arguments.get("tags") or inferred["tags"],
                "category": arguments.get("category") or inferred["category"],
                "limit": arguments.get("limit") or 6,
            }
        normalized.append({**call, "name": name, "arguments": arguments})
    return normalized


async def _plan_tools(
    *,
    messages: list[dict],
    available_tags: list[str],
    categories: list[dict],
    memory: str,
    raw_message: str,
) -> list[dict]:
    """优先让模型规划工具；供应商不可用时稳定回退到本地意图规则。"""

    try:
        calls = await ai_provider.plan_tools(
            messages=messages,
            available_tags=available_tags,
            memory=memory,
        )
    except Exception as exc:  # 第三方能力是可降级依赖，失败不能中断本地图库功能。
        logger.info("AI tool planning fell back to local rules: %s", exc)
        calls = []
    if not calls:
        calls = ai_tools.deterministic_calls(raw_message)
    return _normalize_tool_calls(
        calls,
        raw_message=raw_message,
        available_tags=available_tags,
        categories=categories,
    )


def _build_deterministic_reply(
    *,
    raw_message: str,
    images: list[dict],
    tool_results: list[dict],
    favorite_result: dict | None,
) -> str:
    """把真实工具结果转换为稳定中文回复，不依赖云端模型。"""

    if favorite_result is not None:
        return (
            f"已为你收藏 {len(favorite_result['added'])} 张图片，"
            f"{len(favorite_result['existed'])} 张之前已收藏。"
        )
    if not _has_image_tool_result(tool_results):
        return ""
    if not images:
        return NO_IMAGE_REPLY

    first_tool = next(
        (item.get("tool") for item in tool_results if item.get("tool") in IMAGE_TOOL_NAMES),
        "",
    )
    if first_tool == "get_hot_images":
        lead = "我按图库真实浏览热度为你找到了这些热门图片："
    elif first_tool == "get_latest_images":
        lead = "我按发布时间为你找到了这些最新发布的图片："
    else:
        lead = f"我按“{raw_message}”在图库真实数据里找到了这些图片："

    lines = [lead]
    for index, image in enumerate(images[:6], start=1):
        tags = [item.get("name") for item in image.get("tags", []) if item.get("name")][:4]
        metadata = [
            f"分类：{image['category']['name']}" if image.get("category") else "",
            f"标签：{'、'.join(tags)}" if tags else "",
            f"浏览：{image.get('view_count') or 0}",
            f"收藏：{image.get('favorite_count') or 0}",
        ]
        lines.append(
            f"{index}. 《{image['title']}》（ID：{image['id']}，"
            f"{'，'.join(item for item in metadata if item)}）"
        )
    return _append_favorite_hint("\n".join(lines), images)


async def _find_recommended_images(
    db: AsyncSession,
    *,
    user_id: int,
    keywords: list[str],
    recommended_tags: list[str],
) -> list[dict]:
    """根据结构化关键词推荐图片；标签过严无结果时退回关键词检索。"""

    keyword = " ".join(keywords)
    images = await ai_tools.find_images(
        db,
        user_id=user_id,
        keyword=keyword,
        tags=recommended_tags,
        sort="weight",
        limit=6,
    )
    if images or (not keywords and not recommended_tags):
        return images
    return await ai_tools.find_images(
        db,
        user_id=user_id,
        keyword=keyword,
        sort="weight",
        limit=6,
    )


async def _prepare_conversation(
    db: AsyncSession,
    *,
    user: User,
    conversation_id: int | None,
    user_content: str,
) -> tuple[AiConversation, bool]:
    """校验或创建会话，保存用户消息并提交 SSE 开始事件需要的 ID。"""

    is_new = conversation_id is None
    if conversation_id is not None:
        conversation = await db.scalar(
            select(AiConversation).where(
                AiConversation.id == conversation_id,
                AiConversation.user_id == user.id,
                AiConversation.deleted_at.is_(None),
            )
        )
        if not conversation:
            raise not_found("AI 会话不存在或已删除")
    else:
        conversation = AiConversation(user_id=user.id, title=DEFAULT_TITLE)
        db.add(conversation)
        await db.flush()
        stats = await db.scalar(
            select(UserStat).where(UserStat.user_id == user.id).with_for_update()
        )
        if stats:
            stats.ai_conversation_count += 1

    db.add(
        AiMessage(
            conversation_id=conversation.id,
            user_id=user.id,
            role="user",
            content=user_content,
        )
    )
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    await db.refresh(conversation)
    return conversation, is_new


async def _build_chat_state(
    db: AsyncSession,
    *,
    user: User,
    conversation_id: int | None,
    message: str | None,
) -> dict:
    """完成消息校验、会话准备、历史、分类、标签和记忆装配。"""

    raw_message = str(message or "").strip()
    if not raw_message:
        raise bad_request("消息内容不能为空")
    conversation, is_new = await _prepare_conversation(
        db,
        user=user,
        conversation_id=conversation_id,
        user_content=raw_message,
    )
    history = await _conversation_history(
        db,
        conversation_id=conversation.id,
        user_id=user.id,
    )
    available_tags = await _available_tags(db)
    categories = await _available_categories(db)
    memories = await _memory_context(
        db,
        user_id=user.id,
        conversation_id=conversation.id,
    )
    return {
        "raw_message": raw_message,
        "conversation": conversation,
        "is_new": is_new,
        "history": history,
        "available_tags": available_tags,
        "categories": categories,
        "memories": memories,
    }


async def _finalize_assistant_message(
    db: AsyncSession,
    *,
    user: User,
    state: dict,
    reply: str,
    recommended_tags: list[str],
    recommended_images: list[dict],
    ip_address: str | None,
) -> None:
    """持久化助手回复、统计、活跃时间、审计日志和可降级记忆摘要。"""

    conversation: AiConversation = state["conversation"]
    title = conversation.title
    if state["is_new"]:
        title = (
            await ai_provider.generate_title(
                user_message=state["raw_message"],
                assistant_reply=reply,
            )
        ) or DEFAULT_TITLE

    db.add(
        AiMessage(
            conversation_id=conversation.id,
            user_id=user.id,
            role="assistant",
            content=reply,
            recommended_tags=recommended_tags,
            recommended_image_ids=[item["id"] for item in recommended_images],
        )
    )
    conversation.title = title
    # Express 版仅在首轮更新标题，导致旧会话再次对话后仍排在列表末尾；这里
    # 显式刷新活跃时间，使按 updated_at 倒序的前端列表符合用户直觉。
    conversation.updated_at = datetime.now()
    stats = await db.scalar(
        select(UserStat).where(UserStat.user_id == user.id).with_for_update()
    )
    if stats:
        stats.ai_message_count += 2
    await write_log(
        db,
        actor=user,
        action_type="AI_CONVERSATION_CREATE" if state["is_new"] else "AI_MESSAGE_SEND",
        target_type="ai",
        target_id=conversation.id,
        title="创建 AI 会话" if state["is_new"] else "发送 AI 消息",
        content=f"{user.username} 使用了桃灵助手",
        ip_address=ip_address,
    )
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    await db.refresh(conversation)

    recent_messages = [
        *state["history"][-9:],
        {"role": "assistant", "content": reply},
    ]
    summary = await ai_provider.summarize_memories(
        existing_short=state["memories"]["short"],
        existing_long=state["memories"]["long"],
        messages=recent_messages,
    )
    try:
        await _upsert_memory(
            db,
            user_id=user.id,
            conversation_id=conversation.id,
            memory_type="short",
            content=summary.get("short_memory") or state["memories"]["short"],
        )
        if summary.get("long_memory"):
            await _upsert_memory(
                db,
                user_id=user.id,
                conversation_id=conversation.id,
                memory_type="long",
                content=summary["long_memory"],
            )
        await db.commit()
    except Exception as exc:
        # 记忆属于增强能力；持久化失败不应让已经保存的回复在前端显示为失败。
        await db.rollback()
        logger.warning("Failed to persist AI memory: %s", exc)


async def _tool_execution(
    db: AsyncSession,
    *,
    user: User,
    state: dict,
    ip_address: str | None,
) -> dict:
    """规划并执行本轮工具调用，统一返回图片、工具结果和收藏结果。"""

    blocked_generation = _is_image_generation_request(state["raw_message"])
    calls = (
        ai_tools.deterministic_calls(state["raw_message"])
        if blocked_generation
        else await _plan_tools(
            messages=state["history"],
            available_tags=state["available_tags"],
            categories=state["categories"],
            memory=state["memories"]["text"],
            raw_message=state["raw_message"],
        )
    )
    calls = _normalize_tool_calls(
        calls,
        raw_message=state["raw_message"],
        available_tags=state["available_tags"],
        categories=state["categories"],
    )
    tools = await ai_tools.execute_calls(
        db,
        user=user,
        conversation_id=state["conversation"].id,
        calls=calls,
        ip_address=ip_address,
    )
    tools["blocked_generation"] = blocked_generation
    return tools


async def chat(
    db: AsyncSession,
    *,
    user: User,
    conversation_id: int | None,
    message: str | None,
    ip_address: str | None,
) -> dict:
    """执行非流式对话，并返回与 Vue ``AssistantChatResult`` 一致的数据。"""

    state = await _build_chat_state(
        db,
        user=user,
        conversation_id=conversation_id,
        message=message,
    )
    tools = await _tool_execution(db, user=user, state=state, ip_address=ip_address)
    deterministic_reply = (
        ""
        if tools["blocked_generation"]
        else _build_deterministic_reply(
            raw_message=state["raw_message"],
            images=tools["images"],
            tool_results=tools["tool_results"],
            favorite_result=tools["favorite_result"],
        )
    )
    ai_result = {
        "reply": IMAGE_GENERATION_REPLY if tools["blocked_generation"] else "",
        "recommended_tags": [],
        "search_keywords": [],
        "title": "",
    }
    if deterministic_reply:
        ai_result["reply"] = deterministic_reply
    elif not tools["blocked_generation"]:
        try:
            ai_result = await ai_provider.structured_reply(
                messages=[*state["history"], *_build_tool_messages(tools["tool_results"])],
                available_tags=state["available_tags"],
                memory=state["memories"]["text"],
            )
        except Exception as exc:
            logger.info("AI structured reply fell back to local text: %s", exc)
            ai_result["reply"] = ai_provider.FALLBACK_REPLY

    recommended_images = (
        tools["images"]
        if _has_image_tool_result(tools["tool_results"]) or tools["favorite_result"] is not None
        else await _find_recommended_images(
            db,
            user_id=user.id,
            keywords=ai_result.get("search_keywords") or [],
            recommended_tags=ai_result.get("recommended_tags") or [],
        )
    )
    reply = deterministic_reply or _append_favorite_hint(
        str(ai_result.get("reply") or "").strip(),
        recommended_images,
    )
    recommended_tags = ai_result.get("recommended_tags") or []
    await _finalize_assistant_message(
        db,
        user=user,
        state=state,
        reply=reply,
        recommended_tags=recommended_tags,
        recommended_images=recommended_images,
        ip_address=ip_address,
    )
    return {
        "conversation_id": state["conversation"].id,
        "title": state["conversation"].title,
        "reply": reply,
        "recommended_tags": recommended_tags,
        "recommended_images": recommended_images,
        "tool_results": tools["tool_results"],
    }


async def chat_stream(
    db: AsyncSession,
    *,
    user: User,
    conversation_id: int | None,
    message: str | None,
    ip_address: str | None,
) -> AsyncIterator[tuple[str, dict]]:
    """执行 SSE 对话，依次产出 start/tools/delta/done 事件。"""

    state = await _build_chat_state(
        db,
        user=user,
        conversation_id=conversation_id,
        message=message,
    )
    yield (
        "start",
        {
            "conversation_id": state["conversation"].id,
            "title": state["conversation"].title,
            "is_new": state["is_new"],
            "default_stream": True,
        },
    )
    tools = await _tool_execution(db, user=user, state=state, ip_address=ip_address)
    if tools["tool_results"]:
        yield "tools", {"results": tools["tool_results"]}

    deterministic_reply = (
        ""
        if tools["blocked_generation"]
        else _build_deterministic_reply(
            raw_message=state["raw_message"],
            images=tools["images"],
            tool_results=tools["tool_results"],
            favorite_result=tools["favorite_result"],
        )
    )
    reply = ""
    if deterministic_reply:
        reply = deterministic_reply
        yield "delta", {"delta": reply}
    elif tools["blocked_generation"]:
        reply = IMAGE_GENERATION_REPLY
        yield "delta", {"delta": reply}
    else:
        try:
            async for delta in ai_provider.stream_reply(
                messages=[*state["history"], *_build_tool_messages(tools["tool_results"])],
                available_tags=state["available_tags"],
                memory=state["memories"]["text"],
            ):
                reply += delta
                yield "delta", {"delta": delta}
        except Exception as exc:
            logger.info("AI stream reply fell back to local text: %s", exc)
            reply = ai_provider.FALLBACK_REPLY
            yield "delta", {"delta": reply}

    try:
        ai_result = await ai_provider.structured_reply(
            messages=[
                *state["history"],
                *_build_tool_messages(tools["tool_results"]),
                {"role": "assistant", "content": reply},
                {"role": "user", "content": "请提取本轮推荐标签、图库搜索关键词和短标题。"},
            ],
            available_tags=state["available_tags"],
            memory=state["memories"]["text"],
        )
    except Exception as exc:
        logger.info("AI stream metadata fell back to local values: %s", exc)
        ai_result = {
            "recommended_tags": [],
            "search_keywords": [state["raw_message"]],
        }

    recommended_images = (
        tools["images"]
        if _has_image_tool_result(tools["tool_results"]) or tools["favorite_result"] is not None
        else await _find_recommended_images(
            db,
            user_id=user.id,
            keywords=ai_result.get("search_keywords") or [],
            recommended_tags=ai_result.get("recommended_tags") or [],
        )
    )
    final_reply = deterministic_reply or _append_favorite_hint(reply, recommended_images)
    suffix = final_reply[len(reply) :]
    if suffix:
        yield "delta", {"delta": suffix}
    recommended_tags = ai_result.get("recommended_tags") or []
    await _finalize_assistant_message(
        db,
        user=user,
        state=state,
        reply=final_reply,
        recommended_tags=recommended_tags,
        recommended_images=recommended_images,
        ip_address=ip_address,
    )
    yield (
        "done",
        {
            "conversation_id": state["conversation"].id,
            "title": state["conversation"].title,
            "reply": final_reply,
            "recommended_tags": recommended_tags,
            "recommended_images": recommended_images,
            "tool_results": tools["tool_results"],
        },
    )


async def create_conversation(
    db: AsyncSession,
    *,
    user: User,
    title: str | None,
    ip_address: str | None,
) -> dict:
    """显式创建空会话，并同步用户统计与管理员审计日志。"""

    clean_title = str(title or DEFAULT_TITLE).strip() or DEFAULT_TITLE
    conversation = AiConversation(user_id=user.id, title=clean_title)
    db.add(conversation)
    await db.flush()
    stats = await db.scalar(
        select(UserStat).where(UserStat.user_id == user.id).with_for_update()
    )
    if stats:
        stats.ai_conversation_count += 1
    await write_log(
        db,
        actor=user,
        action_type="AI_CONVERSATION_CREATE",
        target_type="ai",
        target_id=conversation.id,
        title="创建 AI 会话",
        content=f"{user.username} 创建了 AI 会话《{clean_title}》",
        ip_address=ip_address,
    )
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    await db.refresh(conversation)
    return _serialize_conversation(conversation)


def _serialize_conversation(conversation: AiConversation) -> dict:
    """把会话模型转换成前端使用的四个稳定字段。"""

    return {
        "id": conversation.id,
        "title": conversation.title,
        "created_at": conversation.created_at,
        "updated_at": conversation.updated_at,
    }


async def list_conversations(db: AsyncSession, *, user_id: int) -> list[dict]:
    """按最近活动时间倒序返回当前用户的未删除会话。"""

    rows = await db.scalars(
        select(AiConversation)
        .where(
            AiConversation.user_id == user_id,
            AiConversation.deleted_at.is_(None),
        )
        .order_by(AiConversation.updated_at.desc(), AiConversation.id.desc())
    )
    return [_serialize_conversation(item) for item in rows.all()]


async def _require_conversation(
    db: AsyncSession,
    *,
    user_id: int,
    conversation_id: int,
    for_update: bool = False,
) -> AiConversation:
    """读取属于当前用户的有效会话，阻止越权访问其他用户历史。"""

    statement = select(AiConversation).where(
        AiConversation.id == conversation_id,
        AiConversation.user_id == user_id,
        AiConversation.deleted_at.is_(None),
    )
    if for_update:
        statement = statement.with_for_update()
    conversation = await db.scalar(statement)
    if not conversation:
        raise not_found("AI 会话不存在或已删除")
    return conversation


async def list_messages(
    db: AsyncSession,
    *,
    user_id: int,
    conversation_id: int,
) -> list[dict]:
    """返回会话消息，并批量恢复每条助手消息关联的公开推荐图片。"""

    await _require_conversation(
        db,
        user_id=user_id,
        conversation_id=conversation_id,
    )
    messages = list(
        (
            await db.scalars(
                select(AiMessage)
                .where(
                    AiMessage.conversation_id == conversation_id,
                    AiMessage.user_id == user_id,
                    AiMessage.deleted_at.is_(None),
                )
                .order_by(AiMessage.created_at.asc(), AiMessage.id.asc())
            )
        ).all()
    )
    image_ids: list[int] = []
    for message in messages:
        for image_id in ai_tools.normalize_image_ids(
            message.recommended_image_ids or [],
            limit=20,
        ):
            if image_id not in image_ids:
                image_ids.append(image_id)

    images = list(
        (
            await db.scalars(
                select(Image).where(
                    Image.id.in_(image_ids or [-1]),
                    Image.status == "public",
                    Image.deleted_at.is_(None),
                )
            )
        ).all()
    )
    category_map, tags_by_image, favorite_ids = await image_service._load_image_context(
        db,
        images,
        current_user_id=user_id,
    )
    image_map: dict[int, dict] = {}
    for image in images:
        item = image_service.serialize_image(
            image,
            category=category_map.get(image.category_id),
            tags=tags_by_image.get(image.id, []),
            is_favorited=image.id in favorite_ids,
        )
        item["detail_url"] = f"/images/{image.id}"
        image_map[image.id] = item

    return [
        {
            "id": message.id,
            "role": message.role,
            "content": message.content,
            "recommended_tags": message.recommended_tags or [],
            "recommended_image_ids": message.recommended_image_ids or [],
            "recommended_images": [
                image_map[image_id]
                for image_id in ai_tools.normalize_image_ids(
                    message.recommended_image_ids or [],
                    limit=20,
                )
                if image_id in image_map
            ],
            "created_at": message.created_at,
        }
        for message in messages
    ]


async def delete_conversation(
    db: AsyncSession,
    *,
    user: User,
    conversation_id: int,
    ip_address: str | None,
) -> dict:
    """软删除一条会话及其消息，保留审计与统计历史。"""

    conversation = await _require_conversation(
        db,
        user_id=user.id,
        conversation_id=conversation_id,
        for_update=True,
    )
    deleted_at = datetime.now()
    conversation.deleted_at = deleted_at
    await db.execute(
        update(AiMessage)
        .where(
            AiMessage.conversation_id == conversation.id,
            AiMessage.deleted_at.is_(None),
        )
        .values(deleted_at=deleted_at)
    )
    await write_log(
        db,
        actor=user,
        action_type="AI_CONVERSATION_DELETE",
        target_type="ai",
        target_id=conversation.id,
        title="删除 AI 会话",
        content=f"{user.username} 删除了 AI 会话《{conversation.title}》",
        ip_address=ip_address,
    )
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return {}


async def clear_conversations(db: AsyncSession, *, user_id: int) -> dict:
    """软删除当前用户的全部有效会话及其未删除消息。"""

    conversation_ids = list(
        (
            await db.scalars(
                select(AiConversation.id).where(
                    AiConversation.user_id == user_id,
                    AiConversation.deleted_at.is_(None),
                )
            )
        ).all()
    )
    deleted_at = datetime.now()
    await db.execute(
        update(AiConversation)
        .where(
            AiConversation.user_id == user_id,
            AiConversation.deleted_at.is_(None),
        )
        .values(deleted_at=deleted_at)
    )
    if conversation_ids:
        await db.execute(
            update(AiMessage)
            .where(
                AiMessage.conversation_id.in_(conversation_ids),
                AiMessage.deleted_at.is_(None),
            )
            .values(deleted_at=deleted_at)
        )
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return {}
