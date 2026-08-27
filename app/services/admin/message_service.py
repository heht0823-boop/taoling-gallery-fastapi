"""管理后台留言分页、详情、管理员回复与屏蔽业务。"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import bad_request, not_found
from app.models.message import UserMessage
from app.models.user import User
from app.services.log_service import write_log
from app.utils.pagination import normalize_pagination, pagination_payload


def _serialize_admin_message(message: UserMessage, user: User | None) -> dict:
    """输出管理端需要的审核字段及留言作者名称。"""

    return {
        "id": message.id,
        "user_id": message.user_id,
        "username": user.username if user else None,
        "parent_id": message.parent_id,
        "content": message.content,
        "check_status": message.check_status,
        "check_score": message.check_score,
        "check_result": message.check_result,
        "ip_address": message.ip_address,
        "user_agent": message.user_agent,
        "created_at": message.created_at,
        "updated_at": message.updated_at,
    }


async def list_messages(
    db: AsyncSession,
    *,
    page: int,
    page_size: int,
    check_status: str | None,
    parent_id: int | None,
    parent_filter_supplied: bool,
    keyword: str | None,
) -> dict:
    """按审核状态、父留言、正文关键字分页查询未删除留言。"""

    page, page_size, offset = normalize_pagination(page, page_size)
    conditions = [UserMessage.deleted_at.is_(None)]
    if check_status:
        conditions.append(UserMessage.check_status == check_status)
    if parent_filter_supplied:
        conditions.append(
            UserMessage.parent_id == parent_id if parent_id else UserMessage.parent_id.is_(None)
        )
    if keyword and (value := keyword.strip()):
        conditions.append(UserMessage.content.like(f"%{value}%"))
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
        "list": [_serialize_admin_message(message, user) for message, user in rows],
        "pagination": pagination_payload(
            page=page,
            page_size=page_size,
            total=total,
        ),
    }


async def _message_row(
    db: AsyncSession,
    message_id: int,
) -> tuple[UserMessage, User | None]:
    """读取留言及作者；作者被删除时仍允许管理员查看历史留言。"""

    row = (
        await db.execute(
            select(UserMessage, User)
            .outerjoin(User, User.id == UserMessage.user_id)
            .where(
                UserMessage.id == message_id,
                UserMessage.deleted_at.is_(None),
            )
        )
    ).one_or_none()
    if not row:
        raise not_found("留言不存在")
    return row


async def get_message(db: AsyncSession, message_id: int) -> dict:
    """返回留言详情并按时间正序装配全部未删除回复。"""

    message, user = await _message_row(db, message_id)
    reply_rows = (
        await db.execute(
            select(UserMessage, User)
            .outerjoin(User, User.id == UserMessage.user_id)
            .where(
                UserMessage.parent_id == message.id,
                UserMessage.deleted_at.is_(None),
            )
            .order_by(UserMessage.created_at.asc(), UserMessage.id.asc())
        )
    ).all()
    return {
        **_serialize_admin_message(message, user),
        "replies": [_serialize_admin_message(reply, reply_user) for reply, reply_user in reply_rows],
    }


async def reply_message(
    db: AsyncSession,
    *,
    admin: User,
    message_id: int,
    content: str,
    ip_address: str | None,
    user_agent: str | None,
) -> dict:
    """创建管理员审核通过的回复，并与审计日志一起提交。"""

    content = content.strip()
    if not content:
        raise bad_request("回复内容不能为空")
    if len(content) > 2000:
        raise bad_request("回复内容不能超过 2000 个字符")
    parent, _ = await _message_row(db, message_id)
    reply = UserMessage(
        user_id=admin.id,
        parent_id=parent.id,
        content=content,
        check_status="success",
        ip_address=ip_address,
        user_agent=(user_agent or "")[:255] or None,
    )
    db.add(reply)
    await db.flush()
    await write_log(
        db,
        actor=admin,
        action_type="USER_MESSAGE_REPLY",
        target_type="user_message",
        target_id=parent.id,
        title="回复用户留言",
        content=f"{admin.username} 回复了留言 {parent.id}",
        ip_address=ip_address,
    )
    await db.commit()
    await db.refresh(reply)
    return _serialize_admin_message(reply, admin)


async def block_message(
    db: AsyncSession,
    *,
    admin: User,
    message_id: int,
    ip_address: str | None,
) -> dict:
    """把留言标记为 block，使其立即从公开和用户列表中隐藏。"""

    message, user = await _message_row(db, message_id)
    message.check_status = "block"
    await write_log(
        db,
        actor=admin,
        action_type="USER_MESSAGE_BLOCK",
        target_type="user_message",
        target_id=message.id,
        title="屏蔽用户留言",
        content=f"{admin.username} 屏蔽了留言 {message.id}",
        ip_address=ip_address,
    )
    await db.commit()
    await db.refresh(message)
    return _serialize_admin_message(message, user)
