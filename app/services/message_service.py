"""公开留言板、我的留言与内容审核业务。

公开列表只装配一层回复以匹配 Vue 结构；新留言先落为待审状态，再将审核结果与
记录统一提交，外部响应不泄漏供应商原始审核数据。
"""

from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import bad_request
from app.models.message import UserMessage
from app.models.user import User
from app.services import content_security_service
from app.utils.image_url import avatar_variants, normalize_image_url
from app.utils.pagination import normalize_pagination, pagination_payload


def serialize_message_user(user: User | None) -> dict | None:
    if not user:
        return None
    avatar_url = normalize_image_url(user.avatar_url) or None
    return {
        "id": user.id,
        "username": user.username,
        "avatar_url": avatar_url,
        **avatar_variants(avatar_url),
    }


def serialize_public_message(
    message: UserMessage,
    user: User | None,
    *,
    replies: list[dict] | None = None,
) -> dict:
    return {
        "id": message.id,
        "user_id": message.user_id,
        "user": serialize_message_user(user),
        "parent_id": message.parent_id,
        "content": message.content,
        "created_at": message.created_at,
        "updated_at": message.updated_at,
        "replies": replies or [],
    }


async def list_board(
    db: AsyncSession,
    *,
    page: int,
    page_size: int,
    parent_id: int | None = None,
) -> dict:
    """分页返回公开审核通过的留言，并一次性装配一层回复。"""
    page, page_size, offset = normalize_pagination(page, page_size)
    parent_condition = UserMessage.parent_id == parent_id if parent_id else UserMessage.parent_id.is_(None)
    conditions = [
        UserMessage.check_status == "success",
        UserMessage.deleted_at.is_(None),
        parent_condition,
    ]
    total = await db.scalar(select(func.count()).select_from(UserMessage).where(*conditions)) or 0
    rows = (
        await db.execute(
            select(UserMessage, User)
            .outerjoin(User, User.id == UserMessage.user_id)
            .where(*conditions)
            .order_by(UserMessage.created_at.desc(), UserMessage.id.desc())
            .offset(offset)
            .limit(page_size)
        )
    ).all()
    message_ids = [message.id for message, _ in rows]
    replies_by_parent: dict[int, list[dict]] = defaultdict(list)
    if message_ids:
        reply_rows = (
            await db.execute(
                select(UserMessage, User)
                .outerjoin(User, User.id == UserMessage.user_id)
                .where(
                    UserMessage.parent_id.in_(message_ids),
                    UserMessage.check_status == "success",
                    UserMessage.deleted_at.is_(None),
                )
                .order_by(UserMessage.created_at.asc(), UserMessage.id.asc())
            )
        ).all()
        for reply, reply_user in reply_rows:
            replies_by_parent[reply.parent_id].append(serialize_public_message(reply, reply_user))
    return {
        "list": [
            serialize_public_message(
                message,
                user,
                replies=replies_by_parent.get(message.id, []),
            )
            for message, user in rows
        ],
        "pagination": pagination_payload(
            page=page,
            page_size=page_size,
            total=total,
        ),
    }


async def list_mine(
    db: AsyncSession,
    *,
    user_id: int,
    page: int,
    page_size: int,
) -> dict:
    """只向普通用户返回本人审核通过且未删除的留言。"""
    page, page_size, offset = normalize_pagination(page, page_size)
    conditions = [
        UserMessage.user_id == user_id,
        UserMessage.check_status == "success",
        UserMessage.deleted_at.is_(None),
    ]
    total = await db.scalar(select(func.count()).select_from(UserMessage).where(*conditions)) or 0
    rows = (
        await db.execute(
            select(UserMessage, User)
            .outerjoin(User, User.id == UserMessage.user_id)
            .where(*conditions)
            .order_by(UserMessage.created_at.desc(), UserMessage.id.desc())
            .offset(offset)
            .limit(page_size)
        )
    ).all()
    return {
        "list": [serialize_public_message(message, user) for message, user in rows],
        "pagination": pagination_payload(
            page=page,
            page_size=page_size,
            total=total,
        ),
    }


async def create_message(
    db: AsyncSession,
    *,
    user: User,
    content: str,
    parent_id: int | None,
    ip_address: str | None,
    user_agent: str | None,
) -> dict:
    """先持久化待审留言，再更新审核结果，响应不泄漏审核结论。"""
    content = content.strip()
    if not content:
        raise bad_request("留言内容不能为空")
    if len(content) > 2000:
        raise bad_request("留言内容不能超过 2000 个字符")
    if parent_id:
        parent = await db.scalar(
            select(UserMessage).where(
                UserMessage.id == parent_id,
                UserMessage.parent_id.is_(None),
                UserMessage.check_status == "success",
                UserMessage.deleted_at.is_(None),
            )
        )
        if not parent:
            raise bad_request("回复的留言不存在或暂不可回复")

    message = UserMessage(
        user_id=user.id,
        parent_id=parent_id,
        content=content,
        check_status="pending",
        check_score=0,
        ip_address=ip_address,
        user_agent=(user_agent or "")[:255] or None,
    )
    db.add(message)
    await db.commit()
    result = await content_security_service.check_text(
        content=content,
        data_id=f"message-{message.id}",
        user_id=user.id,
    )
    message.check_status = result["status"]
    message.check_score = result["score"]
    message.check_result = result["raw"]
    await db.commit()
    return {"submitted": True}
