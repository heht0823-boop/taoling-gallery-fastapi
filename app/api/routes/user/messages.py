from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_user
from app.core.database import get_db
from app.core.response import api_response, created
from app.models.user import User
from app.schemas.message import MessageCreateIn
from app.services import message_service

router = APIRouter(prefix="/user", tags=["user-messages"])


@router.get("/messages")
async def messages(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=8, alias="pageSize", ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    return api_response(
        await message_service.list_mine(
            db,
            user_id=current_user.id,
            page=page,
            page_size=page_size,
        )
    )


@router.post("/messages")
async def create_message(
    payload: MessageCreateIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    return created(
        await message_service.create_message(
            db,
            user=current_user,
            content=payload.content,
            parent_id=payload.parent_id,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        ),
        "留言提交成功，审核通过后展示",
    )
