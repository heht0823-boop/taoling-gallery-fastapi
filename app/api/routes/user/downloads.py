from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_user
from app.core.database import get_db
from app.core.response import api_response, created
from app.models.user import User
from app.schemas.behavior import ImageIdIn
from app.services import download_service

router = APIRouter(prefix="/user", tags=["user-downloads"])


@router.get("/downloads")
async def downloads(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=12, alias="pageSize", ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    return api_response(
        await download_service.list_downloads(
            db,
            user_id=current_user.id,
            page=page,
            page_size=page_size,
        )
    )


@router.post("/downloads")
async def create_download_alias(
    payload: ImageIdIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    return created(
        await download_service.create_download(
            db,
            user=current_user,
            image_id=payload.image_id,
            ip_address=request.client.host if request.client else None,
        ),
        "下载记录已创建",
    )


@router.delete("/downloads/{record_id}")
async def delete_download(
    record_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    return api_response(
        await download_service.delete_download(
            db,
            user=current_user,
            record_id=record_id,
            ip_address=request.client.host if request.client else None,
        ),
        "下载记录已删除",
    )


@router.delete("/downloads")
async def clear_downloads(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    return api_response(
        await download_service.clear_downloads(
            db,
            user=current_user,
            ip_address=request.client.host if request.client else None,
        ),
        "下载记录已清空",
    )
