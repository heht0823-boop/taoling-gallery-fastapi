"""认证与权限依赖。

统一解析 Cookie 或 Bearer Token，并为公开、登录和管理员接口提供依赖函数。
"""

from fastapi import Depends, Request
from jwt import InvalidTokenError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import forbidden, unauthorized
from app.core.security import decode_access_token, read_token
from app.models.user import User


async def load_user_from_token(token: str, db: AsyncSession) -> User | None:
    """
    根据token加载数据库用户
    不会抛出异常，解析失败/用户不存在/账号异常全部返回None
    :param token: JWT令牌字符串
    :param db: 数据库会话
    :return: 用户模型对象，校验失败返回None
    """
    try:
        # 解码JWT令牌
        payload = decode_access_token(token)
    except InvalidTokenError:
        # token过期、篡改、格式错误，直接返回None
        return None

    # 从载荷取出用户id
    user_id = payload.get("id")
    if not user_id:
        return None

    # 查询用户：id匹配，并且没有被软删除(deleted_at is null)
    result = await db.execute(
        select(User).where(
            User.id == user_id,
            User.deleted_at.is_(None),
        )
    )
    # 查询最多一条，找不到返回None
    user = result.scalar_one_or_none()

    # 用户不存在，或者账号状态不是正常，返回None
    if not user or user.status != "normal":
        return None
    return user


async def optional_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """
    【可选登录依赖】
    有合法token则返回用户对象；无token/token失效返回None，不会抛出异常
    适用场景：游客、登录用户都可以访问的接口
    """
    # 从cookie/header读取token
    token = read_token(request)
    if not token:
        return None
    # 根据token查询用户
    return await load_user_from_token(token, db)


async def require_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    【强制登录依赖】
    必须携带有效登录token，否则抛出401 Unauthorized异常阻断请求
    路由使用: current_user: User = Depends(require_user)
    :raises unauthorized: 未登录 / token失效 / 账号不可用
    :return: 已登录的用户模型对象
    """
    token = read_token(request)
    # 没有token直接401
    if not token:
        raise unauthorized()

    user = await load_user_from_token(token, db)
    # token解析成功，但查不到有效用户，登录状态失效
    if not user:
        raise unauthorized("登录已失效或账号不可用，请重新登录")
    return user


async def require_admin(
    user: User = Depends(require_user),
) -> User:
    """
    【管理员权限依赖】
    嵌套依赖 require_user：先校验必须登录成功，再校验角色为admin
    路由使用: admin: User = Depends(require_admin)
    :raises forbidden: 登录成功，但不是管理员角色，抛出403
    :return: 管理员用户对象
    """
    if user.role != "admin":
        raise forbidden("只有管理员可以访问")
    return user


def client_ip(request: Request) -> str | None:
    """
    【客户端IP提取】
    安全读取请求来源IP；测试环境或无连接上下文时返回None
    :param request: fastapi Request对象
    :return: 客户端IP字符串，无连接信息返回None
    """
    return request.client.host if request.client else None
