from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.core.database import get_db
from app.core.response import api_response, created
from app.models.user import User
from app.schemas.admin import (
    ImageCreateIn,
    ImageRestoreIn,
    ImageStatusIn,
    ImageUpdateIn,
)
from app.services.admin import image_service

router = APIRouter(prefix="/admin", tags=["admin-images"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.post("/files/images")
async def upload_image_file(
    file: UploadFile = File(...),
    _: User = Depends(require_admin),
):
    return created(await image_service.upload_image(file), "图片上传成功")


@router.post("/images")
async def create_image(
    payload: ImageCreateIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    return created(
        await image_service.create_image(
            db,
            admin=admin,
            payload=payload.model_dump(),
            ip_address=_client_ip(request),
        ),
        "图片创建成功",
    )


@router.get("/images")
async def images(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=12, alias="pageSize", ge=1, le=100),
    keyword: str | None = None,
    category_id: int | None = Query(default=None, alias="category_id"),
    category_id_camel: int | None = Query(
        default=None,
        alias="categoryId",
        include_in_schema=False,
    ),
    status: str | None = None,
    tag_id: int | None = Query(default=None, alias="tag_id"),
    tag_id_camel: int | None = Query(
        default=None,
        alias="tagId",
        include_in_schema=False,
    ),
    sort: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    return api_response(
        await image_service.list_images(
            db,
            page=page,
            page_size=page_size,
            keyword=keyword,
            category_id=(
                category_id if category_id is not None else category_id_camel
            ),
            status=status,
            tag_id=tag_id if tag_id is not None else tag_id_camel,
            sort=sort,
        )
    )


@router.get("/images/{image_id}")
async def image_detail(
    image_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    return api_response(await image_service.get_image(db, image_id))


@router.put("/images/{image_id}")
@router.patch("/images/{image_id}")
async def update_image(
    image_id: int,
    payload: ImageUpdateIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    return api_response(
        await image_service.update_image(
            db,
            admin=admin,
            image_id=image_id,
            payload=payload.model_dump(exclude_unset=True),
            ip_address=_client_ip(request),
        ),
        "图片更新成功",
    )


@router.patch("/images/{image_id}/status")
async def update_image_status(
    image_id: int,
    payload: ImageStatusIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    return api_response(
        await image_service.change_status(
            db,
            admin=admin,
            image_id=image_id,
            status=payload.status,
            ip_address=_client_ip(request),
        ),
        "图片状态更新成功",
    )


@router.delete("/images/{image_id}")
async def delete_image(
    image_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    return api_response(
        await image_service.delete_image(
            db,
            admin=admin,
            image_id=image_id,
            ip_address=_client_ip(request),
        ),
        "图片删除成功",
    )


@router.patch("/images/{image_id}/restore")
async def restore_image(
    image_id: int,
    payload: ImageRestoreIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    return api_response(
        await image_service.restore_image(
            db,
            admin=admin,
            image_id=image_id,
            status=payload.status,
            ip_address=_client_ip(request),
        ),
        "图片恢复成功",
    )
