"""登录用户的收藏列表与兼容别名路由。

资源式 ``/images/{id}/favorite`` 和用户式 ``/user/favorites/{id}`` 最终调用
同一事务服务，确保幂等语义、累计计数和审计日志完全一致。
"""

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import client_ip, require_user
from app.core.database import get_db
from app.core.response import api_response, created
from app.models.user import User
from app.schemas.behavior import ImageIdIn
from app.services import favorite_service

router = APIRouter(prefix="/user", tags=["user-favorites"])


@router.get("/favorites")
async def favorites(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=12, alias="pageSize", ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """分页返回当前用户仍可访问的公开图片收藏。"""

    return api_response(
        await favorite_service.list_favorites(
            db,
            user_id=current_user.id,
            page=page,
            page_size=page_size,
        )
    )


@router.post("/favorites")
async def add_favorite_alias(
    payload: ImageIdIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """保留用户式收藏 URL，业务语义与资源式接口一致。"""

    return created(
        await favorite_service.add_favorite(
            db,
            user=current_user,
            image_id=payload.image_id,
            ip_address=client_ip(request),
        ),
        "收藏成功",
    )


@router.delete("/favorites/{image_id}")
async def remove_favorite_alias(
    image_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """保留用户式取消收藏 URL，并保持幂等。"""

    return api_response(
        await favorite_service.remove_favorite(
            db,
            user=current_user,
            image_id=image_id,
            ip_address=client_ip(request),
        ),
        "取消收藏成功",
    )
