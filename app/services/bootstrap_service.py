"""应用启动引导服务。

对齐 Express ``bootstrapService``：数据库连通后检查管理员账号，并为缺失的
管理员统计记录补齐数据。只有首次创建管理员时才要求 ``ADMIN_PASSWORD``，
避免把空密码或示例密码写入数据库。
"""

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_password
from app.models.user import User, UserStat
from app.services.log_service import write_log


async def ensure_admin_user(db: AsyncSession) -> User:
    """返回现有管理员，或根据安全配置创建首个管理员和统计记录。"""

    admin = await db.scalar(
        select(User)
        .where(User.role == "admin", User.deleted_at.is_(None))
        .order_by(User.id.asc())
    )
    if admin:
        stats = await db.scalar(select(UserStat).where(UserStat.user_id == admin.id))
        if not stats:
            # 历史数据库可能只有管理员账号而没有 user_stats；补齐后个人中心和
            # 管理后台统计接口才能稳定返回完整结构。
            db.add(UserStat(user_id=admin.id))
            try:
                await db.commit()
            except Exception:
                await db.rollback()
                raise
        return admin

    if not settings.admin_password:
        raise RuntimeError(
            "数据库中没有管理员账号；首次启动前必须在 .env 配置 ADMIN_PASSWORD"
        )
    duplicate = await db.scalar(
        select(User).where(
            User.deleted_at.is_(None),
            or_(
                User.username == settings.admin_username,
                User.email == settings.admin_email,
            ),
        )
    )
    if duplicate:
        raise RuntimeError(
            "ADMIN_USERNAME 或 ADMIN_EMAIL 已被普通用户占用，请修改启动配置"
        )

    admin = User(
        username=settings.admin_username,
        email=settings.admin_email,
        password_hash=hash_password(settings.admin_password),
        role="admin",
        status="normal",
    )
    db.add(admin)
    await db.flush()
    db.add(UserStat(user_id=admin.id))
    await write_log(
        db,
        actor=admin,
        action_type="ADMIN_BOOTSTRAP",
        target_type="auth",
        target_id=admin.id,
        title="初始化管理员账号",
        content=f"系统创建默认管理员 {admin.username}",
    )
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return admin
