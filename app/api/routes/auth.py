"""注册、登录、退出与当前用户路由。

响应统一包裹为 ``{code, message, data}``，身份令牌沿用 Node 服务的
``taoling_auth`` HttpOnly Cookie，使现有 Vue 鉴权逻辑无需改字段。
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import client_ip, optional_current_user, require_user
from app.core.database import get_db
from app.core.response import api_response, created
from app.core.security import clear_auth_cookie, set_auth_cookie
from app.models.user import User
from app.schemas.auth import LoginIn, RegisterIn
from app.services import auth_service

# 认证模块路由组，统一前缀 /auth，接口文档标签 auth
router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register")
async def register(payload: RegisterIn, request: Request, db: AsyncSession = Depends(get_db)):
    """
    用户注册接口
    完整访问路径 POST /api/auth/register
    :param payload: 请求体，Pydantic模型校验注册入参(username/email/password)
    :param request: FastAPI请求对象，用于获取客户端IP
    :param db: 数据库会话，由Depends注入
    :return: 统一格式响应，用户信息+统计；token写入Set‑Cookie，不返回在body中
    """
    # 调用业务服务层完成注册逻辑
    result = await auth_service.register(
        db,
        username=payload.username,
        email=payload.email,
        password=payload.password,
        ip_address=client_ip(request),
    )
    # pop把token从返回字典取出，不在响应body返回，放到cookie
    token = result.pop("token")
    # 201 Created 成功响应包装
    response = created(result, "注册成功")
    # 设置cookie，把JWT令牌写入响应头Set‑Cookie
    set_auth_cookie(response, token)
    return response


@router.post("/login")
async def login(payload: LoginIn, request: Request, db: AsyncSession = Depends(get_db)):
    """
    用户登录接口，支持用户名/邮箱登录
    完整访问路径 POST /api/auth/login
    :param payload: 登录请求体(account,password)
    :param request: 请求对象，获取客户端IP
    :param db: 数据库会话
    :return: 统一响应，用户信息+统计；token写入cookie
    """
    result = await auth_service.login(
        db,
        account=payload.account,
        password=payload.password,
        ip_address=client_ip(request),
    )
    token = result.pop("token")
    # 包装正常业务响应
    response = api_response(result, "登录成功")
    # 将token设置到cookie返回浏览器
    set_auth_cookie(response, token)
    return response


@router.post("/logout")
async def logout(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(optional_current_user),
):
    """
    用户退出登录
    完整访问路径 POST /api/auth/logout
    可选登录依赖：未登录访问不会抛异常，直接返回成功
    只做两件事：记录退出日志、清除浏览器端cookie；JWT服务端无法作废
    :param request: 请求对象，获取客户端IP
    :param db: 数据库会话
    :param current_user: 可选登录产出用户对象，无有效token为None
    :return: 空数据成功响应
    """
    data = await auth_service.logout(
        db,
        user=current_user,
        ip_address=client_ip(request),
    )
    response = api_response(data, "退出登录成功")
    # 设置cookie过期，清除浏览器保存的认证cookie
    clear_auth_cookie(response)
    return response


@router.get("/me")
async def me(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """
    获取当前登录用户个人信息+统计数据
    完整访问路径 GET /api/auth/me
    强制登录依赖：无/无效token直接抛出401拦截请求
    :param db: 数据库会话
    :param current_user: 强制登录产出当前登录用户ORM对象
    :return: 用户信息与统计数据
    """
    return api_response(await auth_service.get_user_with_stats(db, current_user.id))
