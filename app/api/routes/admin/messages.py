"""管理后台留言审核列表、详情、回复与屏蔽路由。"""

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import client_ip, require_admin
from app.core.database import get_db
from app.core.response import api_response, created
from app.models.user import User
from app.schemas.admin import AdminMessageReplyIn
from app.services.admin import message_service

router = APIRouter(prefix="/admin", tags=["admin-messages"])


@router.get("/messages")
async def messages(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=12, alias="pageSize", ge=1, le=100),
    check_status: str | None = None,
    parent_id: int | None = Query(default=None, alias="parent_id"),
    keyword: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """保留 ``parent_id`` 是否显式传入的信息，区分顶层筛选与不筛选。"""

    return api_response(
        await message_service.list_messages(
            db,
            page=page,
            page_size=page_size,
            check_status=check_status,
            parent_id=parent_id,
            parent_filter_supplied="parent_id" in request.query_params,
            keyword=keyword,
        )
    )


@router.get("/messages/{message_id}")
async def message_detail(
    message_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """读取留言及全部回复详情。"""

    return api_response(await message_service.get_message(db, message_id))


@router.post("/messages/{message_id}/replies")
async def reply_message(
    message_id: int,
    payload: AdminMessageReplyIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """创建一条管理员回复并返回 201。"""

    return created(
        await message_service.reply_message(
            db,
            admin=admin,
            message_id=message_id,
            content=payload.content,
            ip_address=client_ip(request),
            user_agent=request.headers.get("user-agent"),
        ),
        "回复成功",
    )


@router.delete("/messages/{message_id}")
async def block_message(
    message_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """将留言审核状态改为 block。"""

    return api_response(
        await message_service.block_message(
            db,
            admin=admin,
            message_id=message_id,
            ip_address=client_ip(request),
        ),
        "留言已屏蔽",
    )
