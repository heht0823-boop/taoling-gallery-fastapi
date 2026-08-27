"""管理后台用户查询、状态控制与软删除路由。"""

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import client_ip, require_admin
from app.core.database import get_db
from app.core.response import api_response
from app.models.user import User
from app.schemas.admin import UserStatusIn
from app.services.admin import user_service

router = APIRouter(prefix="/admin", tags=["admin-users"])


@router.get("/users")
async def users(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=12, alias="pageSize", ge=1, le=100),
    keyword: str | None = None,
    role: str | None = None,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """分页筛选未删除用户。"""

    return api_response(
        await user_service.list_users(
            db,
            page=page,
            page_size=page_size,
            keyword=keyword,
            role=role,
            status=status,
        )
    )


@router.get("/users/{user_id}")
async def user_detail(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """返回用户资料及完整统计。"""

    return api_response(await user_service.get_user(db, user_id))


@router.patch("/users/{user_id}/status")
async def update_user_status(
    user_id: int,
    payload: UserStatusIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """启用或禁用指定用户。"""

    return api_response(
        await user_service.update_user_status(
            db,
            admin=admin,
            user_id=user_id,
            status=payload.status,
            ip_address=client_ip(request),
        ),
        "用户状态更新成功",
    )


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """软删除指定用户。"""

    return api_response(
        await user_service.delete_user(
            db,
            admin=admin,
            user_id=user_id,
            ip_address=client_ip(request),
        ),
        "用户删除成功",
    )
