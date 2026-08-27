"""管理后台分类分页、创建、修改和安全删除路由。"""

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.core.database import get_db
from app.core.response import api_response, created
from app.models.user import User
from app.schemas.admin import CategoryCreateIn, CategoryUpdateIn
from app.services.admin import taxonomy_service

router = APIRouter(prefix="/admin", tags=["admin-categories"])


def _client_ip(request: Request) -> str | None:
    """安全读取客户端 IP，供管理员审计日志记录。"""

    return request.client.host if request.client else None


@router.get("/categories")
async def categories(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=12, alias="pageSize", ge=1, le=100),
    keyword: str | None = None,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """分页查询分类及有效图片引用数。"""

    return api_response(
        await taxonomy_service.list_categories(
            db,
            page=page,
            page_size=page_size,
            keyword=keyword,
            status=status,
        )
    )


@router.post("/categories")
async def create_category(
    payload: CategoryCreateIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """创建分类并返回 201。"""

    return created(
        await taxonomy_service.create_category(
            db,
            admin=admin,
            name=payload.name,
            sort_order=payload.sort_order,
            status=payload.status,
            ip_address=_client_ip(request),
        ),
        "分类创建成功",
    )


@router.put("/categories/{category_id}")
@router.patch("/categories/{category_id}")
async def update_category(
    category_id: int,
    payload: CategoryUpdateIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """兼容 PUT/PATCH 局部更新分类。"""

    return api_response(
        await taxonomy_service.update_category(
            db,
            admin=admin,
            category_id=category_id,
            updates=payload.model_dump(exclude_unset=True),
            ip_address=_client_ip(request),
        ),
        "分类更新成功",
    )


@router.delete("/categories/{category_id}")
async def delete_category(
    category_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """在无图片引用时软删除分类。"""

    return api_response(
        await taxonomy_service.delete_category(
            db,
            admin=admin,
            category_id=category_id,
            ip_address=_client_ip(request),
        ),
        "分类删除成功",
    )
