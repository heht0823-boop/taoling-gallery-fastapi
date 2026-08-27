from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import bad_request, conflict, unauthorized
from app.core.security import hash_password, verify_password
from app.models.user import User
from app.services.auth_service import get_user_with_stats
from app.services.log_service import write_log
from app.utils.image_url import normalize_image_url


async def update_profile(
    db: AsyncSession,
    *,
    user_id: int,
    updates: dict,
    ip_address: str | None,
) -> dict:
    """更新当前用户资料，完成标准化、查重和审计后统一提交。"""
    allowed_updates = {
        key: value
        for key, value in updates.items()
        if key in {"username", "email", "avatar_url"}
    }
    if not allowed_updates:
        raise bad_request("请至少提交一个需要修改的资料字段")

    if "username" in allowed_updates:
        username = str(allowed_updates["username"] or "").strip()
        if not username:
            raise bad_request("用户名不能为空")
        allowed_updates["username"] = username
    if "email" in allowed_updates:
        allowed_updates["email"] = str(allowed_updates["email"] or "").strip() or None
    if "avatar_url" in allowed_updates:
        allowed_updates["avatar_url"] = (
            normalize_image_url(allowed_updates["avatar_url"]) or None
        )

    duplicate_filters = []
    if allowed_updates.get("username"):
        duplicate_filters.append(User.username == allowed_updates["username"])
    if allowed_updates.get("email"):
        duplicate_filters.append(User.email == allowed_updates["email"])
    if duplicate_filters:
        duplicate = await db.scalar(
            select(User).where(
                User.id != user_id,
                User.deleted_at.is_(None),
                or_(*duplicate_filters),
            )
        )
        if duplicate and duplicate.username == allowed_updates.get("username"):
            raise conflict("用户名已被使用")
        if duplicate and duplicate.email == allowed_updates.get("email"):
            raise conflict("邮箱已被使用")

    user = await db.scalar(
        select(User)
        .where(User.id == user_id, User.deleted_at.is_(None))
        .with_for_update()
    )
    if not user:
        raise unauthorized("当前登录用户不存在")
    for key, value in allowed_updates.items():
        setattr(user, key, value)
    await write_log(
        db,
        actor=user,
        action_type="USER_PROFILE_UPDATE",
        target_type="user",
        target_id=user.id,
        title="修改个人资料",
        content=f"{user.username} 修改了个人资料",
        ip_address=ip_address,
    )
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise conflict("用户名或邮箱已被使用") from exc
    return await get_user_with_stats(db, user.id)


async def update_password(
    db: AsyncSession,
    *,
    user_id: int,
    old_password: str,
    new_password: str,
    ip_address: str | None,
) -> dict:
    """校验旧密码并保存新密码哈希。"""
    if not old_password or not new_password:
        raise bad_request("旧密码和新密码不能为空")
    if len(new_password) < 6:
        raise bad_request("新密码长度不能少于 6 位")

    user = await db.scalar(
        select(User)
        .where(User.id == user_id, User.deleted_at.is_(None))
        .with_for_update()
    )
    if not user:
        raise unauthorized("当前登录用户不存在")
    if not verify_password(old_password, user.password_hash):
        raise unauthorized("旧密码不正确")

    user.password_hash = hash_password(new_password)
    await write_log(
        db,
        actor=user,
        action_type="USER_PASSWORD_UPDATE",
        target_type="user",
        target_id=user.id,
        title="修改密码",
        content=f"{user.username} 修改了密码",
        ip_address=ip_address,
    )
    await db.commit()
    return {}
