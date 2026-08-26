from datetime import datetime
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import bad_request, conflict, unauthorized
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User, UserStat
from app.services.log_service import write_log


def serialize_stats(stats: UserStat | None) -> dict:
    """
    将用户统计ORM模型序列化为返回字典
    stats为None时全部填充0，避免前端拿到null
    :param stats: 用户统计数据ORM对象
    :return: 统计信息字典
    """
    return {
        "favorite_count": stats.favorite_count if stats else 0,
        "download_count": stats.download_count if stats else 0,
        "view_count": stats.view_count if stats else 0,
        "ai_conversation_count": stats.ai_conversation_count if stats else 0,
        "ai_message_count": stats.ai_message_count if stats else 0,
    }


def serialize_user(user: User) -> dict:
    """
    将User ORM模型转为对外输出字典，过滤敏感字段（密码哈希不返回）
    :param user: 用户ORM实例
    :return: 用户信息字典
    """
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role": user.role,
        "status": user.status,
        "avatar_url": user.avatar_url,
        "last_login_at": user.last_login_at,
        "created_at": user.created_at,
    }


async def get_user_with_stats(db: AsyncSession, user_id: int) -> dict:
    """
    根据用户ID查询用户+关联的用户统计数据，预加载关联表
    :param db: 数据库会话
    :param user_id: 用户ID
    :raises unauthorized: 用户不存在/已软删除
    :return: {"user":用户信息,"stats":统计信息}
    """
    result = await db.execute(
        select(User)
        .options(selectinload(User.stats))  # 预加载关联UserStat，避免N+1查询
        .where(User.id == user_id, User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise unauthorized("当前登录用户不存在")
    return {
        "user": serialize_user(user),
        "stats": serialize_stats(user.stats),
    }


async def register(
    db: AsyncSession,
    *,
    username: str,
    email: str | None,
    password: str,
    ip_address: str | None,
) -> dict:
    """
    用户注册业务逻辑
    :param db: 数据库会话
    :param username: 用户名
    :param email: 邮箱，可以为空
    :param password: 原始明文密码
    :param ip_address: 客户端IP，用于写操作日志
    :raises bad_request: 参数为空、密码长度不足
    :raises conflict: 用户名/邮箱重复
    :return: token + 用户信息+统计数据
    """
    # 去除首尾空格
    username = username.strip()
    email = email.strip() if email else None

    # 参数基础校验
    if not username or not password:
        raise bad_request("用户名和密码不能为空")
    if len(password) < 6:
        raise bad_request("密码长度不能少于 6 位")

    # 构建查重条件：用户名必查，邮箱存在则加入条件
    filters = [User.username == username]
    if email:
        filters.append(User.email == email)

    # 查询是否存在重复账号，排除软删除用户
    duplicate = await db.scalar(
        select(User).where(
            User.deleted_at.is_(None),
            or_(*filters),
        )
    )
    if duplicate and duplicate.username == username:
        raise conflict("用户名已被使用")
    if email and duplicate and duplicate.email == email:
        raise conflict("邮箱已被使用")

    # 创建用户模型，密码哈希存储，不保存明文
    user = User(
        username=username,
        email=email,
        password_hash=hash_password(password),
        role="user",
        status="normal",
    )
    db.add(user)
    await db.flush()  # flush：拿到数据库自增user.id，还未真正提交事务

    # 创建该用户对应的统计记录
    db.add(UserStat(user_id=user.id))

    # 写入注册操作日志，db.add仅加入会话队列
    await write_log(
        db,
        actor=user,
        action_type="USER_REGISTER",
        target_type="auth",
        target_id=user.id,
        title="用户注册",
        content=f"{user.username} 注册了账号",
        ip_address=ip_address,
    )
    # 统一事务提交：用户、统计、日志一起落库
    await db.commit()

    # 查询完整用户与统计信息返回
    fresh = await get_user_with_stats(db, user.id)
    return {
        "token": create_access_token(user.id, user.role),
        **fresh,
    }


async def login(
    db: AsyncSession,
    *,
    account: str,
    password: str,
    ip_address: str | None,
) -> dict:
    """
    用户登录，支持用户名/邮箱两种账号登录
    :param db: 数据库会话
    :param account: 用户名或者邮箱
    :param password: 明文密码
    :param ip_address: 客户端IP，记录操作日志
    :raises bad_request: 账号密码为空
    :raises unauthorized: 用户不存在、账号禁用、密码错误
    :return: token + 用户信息+统计数据
    """
    if not account or not password:
        raise bad_request("账号和密码不能为空")

    # 根据用户名或邮箱查询用户，预加载统计数据，过滤软删除
    user = await db.scalar(
        select(User)
        .options(selectinload(User.stats))
        .where(
            User.deleted_at.is_(None),
            or_(User.username == account, User.email == account),
        )
    )
    if not user:
        raise unauthorized("账号或密码错误")
    if user.status != "normal":
        raise unauthorized("账号已被禁用，请联系管理员")
    # 校验密码哈希
    if not verify_password(password, user.password_hash):
        raise unauthorized("账号或密码错误")

    # 更新最后登录时间
    user.last_login_at = datetime.now()
    # 写入登录日志
    await write_log(
        db,
        actor=user,
        action_type="USER_LOGIN",
        target_type="auth",
        target_id=user.id,
        title="用户登录",
        content=f"{user.username} 登录了系统",
        ip_address=ip_address,
    )
    await db.commit()

    fresh = await get_user_with_stats(db, user.id)
    return {
        "token": create_access_token(user.id, user.role),
        **fresh,
    }


async def logout(db: AsyncSession, *, user: User | None, ip_address: str | None) -> dict:
    """
    用户退出登录
    > JWT无服务端session，logout仅记录操作日志，不会使token失效
    :param db: 数据库会话
    :param user: 当前登录用户，可选（游客访问logout接口user=None）
    :param ip_address: 客户端IP
    :return: 空字典
    """
    # 未登录用户调用退出接口，直接返回
    if not user:
        return {}
    await write_log(
        db,
        actor=user,
        action_type="USER_LOGOUT",
        target_type="auth",
        target_id=user.id,
        title="退出登录",
        content=f"{user.username} 退出登录",
        ip_address=ip_address,
    )
    await db.commit()
    return {}
