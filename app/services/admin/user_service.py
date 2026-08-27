"""管理后台用户分页、详情、禁用与软删除业务。

所有查询过滤已删除用户；管理员不能禁用或删除自己的账号，防止后台失去当前
操作入口。用户统计作为嵌套 ``stats`` 一次性装配给前端。
"""

from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import bad_request, not_found
from app.models.user import User
from app.services.auth_service import serialize_stats, serialize_user
from app.services.log_service import write_log
from app.utils.pagination import normalize_pagination, pagination_payload


def _serialize_admin_user(user: User) -> dict:
    """在公开用户字段基础上附加管理端需要的完整统计。"""

    return {
        **serialize_user(user),
        "stats": serialize_stats(user.stats),
    }


async def list_users(
    db: AsyncSession,
    *,
    page: int,
    page_size: int,
    keyword: str | None,
    role: str | None,
    status: str | None,
) -> dict:
    """按账号关键字、角色和状态分页查询未删除用户。"""

    page, page_size, offset = normalize_pagination(page, page_size)
    conditions = [User.deleted_at.is_(None)]
    if keyword and (value := keyword.strip()):
        search = f"%{value}%"
        conditions.append(or_(User.username.like(search), User.email.like(search)))
    if role:
        conditions.append(User.role == role)
    if status:
        conditions.append(User.status == status)
    total = await db.scalar(select(func.count()).select_from(User).where(*conditions)) or 0
    users = list(
        (
            await db.scalars(
                select(User)
                .options(selectinload(User.stats))
                .where(*conditions)
                .order_by(User.created_at.desc(), User.id.desc())
                .offset(offset)
                .limit(page_size)
            )
        ).all()
    )
    return {
        "list": [_serialize_admin_user(user) for user in users],
        "pagination": pagination_payload(
            page=page,
            page_size=page_size,
            total=total,
        ),
    }


async def get_user(db: AsyncSession, user_id: int) -> dict:
    """读取一名有效用户及其统计详情。"""

    user = await db.scalar(
        select(User).options(selectinload(User.stats)).where(User.id == user_id, User.deleted_at.is_(None))
    )
    if not user:
        raise not_found("用户不存在")
    return _serialize_admin_user(user)


async def update_user_status(
    db: AsyncSession,
    *,
    admin: User,
    user_id: int,
    status: str,
    ip_address: str | None,
) -> dict:
    """启用/禁用目标用户，并禁止管理员锁定自己的当前账号。"""

    if status not in {"normal", "disabled"}:
        raise bad_request("用户状态只能是 normal 或 disabled")
    if admin.id == user_id:
        raise bad_request("管理员不能禁用自己的账号")
    user = await db.scalar(select(User).where(User.id == user_id, User.deleted_at.is_(None)))
    if not user:
        raise not_found("用户不存在")
    user.status = status
    await write_log(
        db,
        actor=admin,
        action_type="USER_STATUS_CHANGE",
        target_type="user",
        target_id=user.id,
        title="修改用户状态",
        content=f"{admin.username} 将用户 {user.username} 状态改为 {status}",
        ip_address=ip_address,
    )
    await db.commit()
    return await get_user(db, user.id)


async def delete_user(
    db: AsyncSession,
    *,
    admin: User,
    user_id: int,
    ip_address: str | None,
) -> dict:
    """软删除目标用户并禁用登录，历史业务记录继续保留。"""

    if admin.id == user_id:
        raise bad_request("管理员不能删除自己的账号")
    user = await db.scalar(select(User).where(User.id == user_id, User.deleted_at.is_(None)))
    if not user:
        raise not_found("用户不存在")
    user.deleted_at = datetime.now()
    user.status = "disabled"
    await write_log(
        db,
        actor=admin,
        action_type="USER_DELETE",
        target_type="user",
        target_id=user.id,
        title="删除用户",
        content=f"{admin.username} 删除用户 {user.username}",
        ip_address=ip_address,
    )
    await db.commit()
    return {}
