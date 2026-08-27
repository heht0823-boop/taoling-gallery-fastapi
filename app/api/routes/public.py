from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import optional_current_user, require_user
from app.core.database import get_db
from app.core.response import api_response, created
from app.models.user import User
from app.schemas.behavior import ImageViewIn
from app.services import download_service, favorite_service, image_service, view_service

router = APIRouter(tags=["public"])

THUMBNAIL_CACHE_HEADERS = {
    "Cache-Control": "public, max-age=2592000, immutable",
}


def _parse_tag_ids(*values: int | str | None) -> list[int]:
    tag_ids: set[int] = set()
    for value in values:
        if value is None:
            continue
        for item in str(value).split(","):
            try:
                tag_id = int(item.strip())
            except ValueError:
                continue
            if tag_id > 0:
                tag_ids.add(tag_id)
    return sorted(tag_ids)


@router.get("/categories")
async def categories(db: AsyncSession = Depends(get_db)):
    return api_response(await image_service.list_categories(db))


@router.get("/tags")
async def tags(
    keyword: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    return api_response(
        await image_service.list_tags(db, keyword=keyword, limit=limit)
    )


@router.get("/images")
async def images(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=12, alias="pageSize", ge=1, le=100),
    page_size_snake: int | None = Query(
        default=None,
        alias="page_size",
        ge=1,
        le=100,
        include_in_schema=False,
    ),
    keyword: str | None = None,
    category_id: int | None = Query(default=None, alias="category_id"),
    category_id_camel: int | None = Query(
        default=None,
        alias="categoryId",
        include_in_schema=False,
    ),
    tag_id: int | None = Query(default=None, alias="tag_id"),
    tag_ids: str | None = Query(default=None, alias="tag_ids"),
    tag_ids_camel: str | None = Query(
        default=None,
        alias="tagIds",
        include_in_schema=False,
    ),
    aspect_ratio: str | None = Query(default=None, alias="aspect_ratio"),
    sort: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(optional_current_user),
):
    return api_response(
        await image_service.list_images(
            db,
            current_user_id=current_user.id if current_user else None,
            page=page,
            page_size=page_size_snake or page_size,
            keyword=keyword,
            category_id=category_id if category_id is not None else category_id_camel,
            tag_ids=_parse_tag_ids(tag_id, tag_ids, tag_ids_camel),
            aspect_ratio=aspect_ratio,
            sort=sort,
        )
    )


@router.get("/images/{image_id}/thumbnail")
async def image_thumbnail(
    image_id: int,
    width_short: int | None = Query(default=None, alias="w", ge=32, le=2000),
    width: int | None = Query(default=None, ge=32, le=2000),
    image_format: str | None = Query(default=None, alias="format"),
    quality_short: int | None = Query(default=None, alias="q", ge=35, le=95),
    quality: int | None = Query(default=None, ge=35, le=95),
    db: AsyncSession = Depends(get_db),
):
    result = await image_service.get_image_thumbnail(
        db,
        image_id=image_id,
        width=width_short or width,
        image_format=image_format,
        quality=quality_short or quality,
    )
    if result["type"] == "redirect":
        return RedirectResponse(
            result["url"],
            status_code=302,
            headers=THUMBNAIL_CACHE_HEADERS,
        )
    return FileResponse(
        result["path"],
        media_type=result["content_type"],
        headers=THUMBNAIL_CACHE_HEADERS,
    )


@router.get("/images/{image_id}")
async def image_detail(
    image_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(optional_current_user),
):
    return api_response(
        await image_service.get_public_image(
            db,
            image_id=image_id,
            current_user_id=current_user.id if current_user else None,
        )
    )


@router.post("/images/{image_id}/view")
async def create_image_view(
    image_id: int,
    payload: ImageViewIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(optional_current_user),
):
    return api_response(
        await view_service.record_view(
            db,
            image_id=image_id,
            user_id=current_user.id if current_user else None,
            visitor_id=payload.visitor_id,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        ),
        "浏览记录已保存",
    )


@router.post("/images/{image_id}/favorite")
async def add_image_favorite(
    image_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    return created(
        await favorite_service.add_favorite(
            db,
            user=current_user,
            image_id=image_id,
            ip_address=request.client.host if request.client else None,
        ),
        "收藏成功",
    )


@router.delete("/images/{image_id}/favorite")
async def remove_image_favorite(
    image_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    return api_response(
        await favorite_service.remove_favorite(
            db,
            user=current_user,
            image_id=image_id,
            ip_address=request.client.host if request.client else None,
        ),
        "取消收藏成功",
    )


@router.post("/images/{image_id}/download")
async def create_image_download(
    image_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    return created(
        await download_service.create_download(
            db,
            user=current_user,
            image_id=image_id,
            ip_address=request.client.host if request.client else None,
        ),
        "下载记录已创建",
    )


@router.get("/images/{image_id}/related")
async def related(
    image_id: int,
    limit: int = Query(default=6, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(optional_current_user),
):
    return api_response(
        await image_service.related_images(
            db,
            image_id=image_id,
            current_user_id=current_user.id if current_user else None,
            limit=limit,
        )
    )
