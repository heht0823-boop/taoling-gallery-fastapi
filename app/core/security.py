"""密码哈希、JWT 和认证 Cookie 工具。"""

import re
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Request, Response

from app.core.config import settings


def hash_password(password: str) -> str:
    """
    使用 bcrypt 对明文密码进行哈希加密
    :param password: 用户明文密码
    :return: bcrypt哈希后的密码字符串
    """
    hashed = bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt(rounds=10),  # salt 计算轮数，10为常规安全值
    )
    return hashed.decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """
    校验明文密码与存储的bcrypt哈希是否匹配
    :param password: 用户输入明文密码
    :param password_hash: 数据库存储的哈希密码
    :return: 匹配返回True，不匹配返回False
    """
    return bcrypt.checkpw(
        password.encode("utf-8"),
        password_hash.encode("utf-8"),
    )


def parse_duration(value: str) -> timedelta:
    """
    解析时间周期字符串，例如：30s、15m、2h、7d，转为timedelta对象
    :param value: 时间字符串，数字+单位 s/m/h/d
    :raises ValueError: 格式不合法抛出异常
    :return: timedelta时间对象
    """
    match = re.fullmatch(r"(\d+)([smhd])", value.strip())
    if not match:
        raise ValueError(f"Unsupported duration: {value}")
    amount = int(match.group(1))
    unit = match.group(2)
    unit_map = {
        "s": timedelta(seconds=amount),
        "m": timedelta(minutes=amount),
        "h": timedelta(hours=amount),
        "d": timedelta(days=amount),
    }
    return unit_map[unit]


def create_access_token(user_id: int, role: str) -> str:
    """
    生成JWT访问令牌
    payload包含：用户id、角色、签发时间iat、过期时间exp
    :param user_id: 用户ID
    :param role: 用户角色字符串
    :return: JWT token字符串
    """
    now = datetime.now(timezone.utc)
    expire = now + parse_duration(settings.jwt_expires_in)
    return jwt.encode(
        {
            "id": user_id,
            "role": role,
            "iat": int(now.timestamp()),  # token签发时间戳 UTC
            "exp": int(expire.timestamp()),  # token过期时间戳 UTC
        },
        settings.jwt_secret,
        algorithm="HS256",
    )


def decode_access_token(token: str) -> dict:
    """
    解析JWT token，校验签名与exp过期
    注意：jwt.decode会自动校验exp过期时间，过期直接抛出ExpiredSignatureError
    :param token: jwt token字符串
    :return: payload字典
    """
    return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])


def read_token(request: Request) -> str | None:
    """
    从请求中读取token，优先读取Cookie，其次读取Authorization Bearer头
    :param request: fastapi Request对象
    :return: token字符串，无token返回None
    """
    # 优先从cookie获取token
    cookie_token = request.cookies.get(settings.auth_cookie_name)
    if cookie_token:
        return cookie_token
    # 其次读取 Header: Authorization: Bearer xxx
    authorization = request.headers.get("Authorization", "")
    if authorization.startswith("Bearer "):
        return authorization[7:]
    return None


def set_auth_cookie(response: Response, token: str) -> None:
    """
    设置认证Cookie，存储JWT
    httponly: JS无法读取，防御XSS；secure: https才发送；samesite防御CSRF
    :param response: fastapi Response对象
    :param token: jwt访问令牌
    """
    max_age = int(parse_duration(settings.auth_cookie_max_age).total_seconds())
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=token,
        max_age=max_age,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite=settings.auth_cookie_samesite,
        path="/",
        domain=settings.auth_cookie_domain or None,
    )


def clear_auth_cookie(response: Response) -> None:
    """
    清除认证Cookie，用于登出接口
    :param response: fastapi Response对象
    """
    response.delete_cookie(
        key=settings.auth_cookie_name,
        path="/",
        domain=settings.auth_cookie_domain or None,
    )
