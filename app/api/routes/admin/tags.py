"""管理后台标签分页、创建、修改和关联保护删除路由。"""

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import client_ip, require_admin
from app.core.database import get_db
from app.core.response import api_response, created
from app.models.user import User
from app.schemas.admin import TagCreateIn, TagUpdateIn
from app.services.admin import taxonomy_service

router = APIRouter(prefix="/admin", tags=["admin-tags"])


@router.get("/tags")
async def tags(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=12, alias="pageSize", ge=1, le=100),
    keyword: str | None = None,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """分页查询标签及其引用计数。"""

    return api_response(
        await taxonomy_service.list_tags(
            db,
            page=page,
            page_size=page_size,
            keyword=keyword,
            status=status,
        )
    )


@router.post("/tags")
async def create_tag(
    payload: TagCreateIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """创建标签并返回 201。"""

    return created(
        await taxonomy_service.create_tag(
            db,
            admin=admin,
            name=payload.name,
            color=payload.color,
            status=payload.status,
            ip_address=client_ip(request),
        ),
        "标签创建成功",
    )


@router.put("/tags/{tag_id}")
@router.patch("/tags/{tag_id}")
async def update_tag(
    tag_id: int,
    payload: TagUpdateIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """兼容 PUT/PATCH 局部更新标签。"""

    return api_response(
        await taxonomy_service.update_tag(
            db,
            admin=admin,
            tag_id=tag_id,
            updates=payload.model_dump(exclude_unset=True),
            ip_address=client_ip(request),
        ),
        "标签更新成功",
    )


@router.delete("/tags/{tag_id}")
async def delete_tag(
    tag_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """在无图片关联时软删除标签。"""

    return api_response(
        await taxonomy_service.delete_tag(
            db,
            admin=admin,
            tag_id=tag_id,
            ip_address=client_ip(request),
        ),
        "标签删除成功",
    )
