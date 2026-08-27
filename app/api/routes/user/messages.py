"""当前用户留言查询与创建路由。

普通用户只能读取本人审核通过的未删除留言；创建接口不会把内容安全审核的
内部结论直接暴露给客户端，保持原 Node 响应契约。
"""

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
    """分页读取当前用户审核通过且未删除的留言。"""

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
    """创建待审留言并返回不泄漏审核细节的公开字段。"""

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
