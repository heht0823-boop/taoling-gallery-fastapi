"""登录用户的桃灵助手路由。

同时暴露 ``/api/ai/*`` 与 ``/api/user/ai/*`` 两套 Express 兼容路径。聊天默认
使用 SSE；只有 query 或 JSON body 显式传入 ``stream=false`` 时返回普通 JSON。
"""

import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import client_ip, require_user
from app.core.database import get_db
from app.core.exceptions import AppError
from app.core.response import api_response, created
from app.models.user import User
from app.schemas.ai import AiChatIn, AiConversationCreateIn
from app.services import ai_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ai-assistant"])


def _should_stream(query_value: str | None, body_value: bool | None) -> bool:
    """query 参数优先；仅显式 false/0 时关闭 Express 默认流式响应。"""

    value: object = query_value if query_value is not None else body_value
    return value not in {False, 0, "false", "0"}


def _sse_event(event: str, data: dict) -> str:
    """把事件名称和可 JSON 序列化数据编码成标准 SSE 事件块。"""

    payload = json.dumps(
        jsonable_encoder(data),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return f"event: {event}\ndata: {payload}\n\n"


async def _stream_events(
    db: AsyncSession,
    *,
    user: User,
    payload: AiChatIn,
    ip_address: str | None,
) -> AsyncIterator[str]:
    """转发业务事件，并把流开始后的异常转换成前端可处理的 error 事件。"""

    try:
        async for event, data in ai_service.chat_stream(
            db,
            user=user,
            conversation_id=payload.conversation_id,
            message=payload.message,
            ip_address=ip_address,
        ):
            yield _sse_event(event, data)
    except AppError as exc:
        await db.rollback()
        yield _sse_event(
            "error",
            {"code": exc.status_code, "message": exc.message, "data": exc.data},
        )
    except Exception as exc:
        await db.rollback()
        logger.exception("AI streaming request failed", exc_info=exc)
        yield _sse_event(
            "error",
            {"code": 500, "message": "AI 流式回复失败", "data": {}},
        )


@router.post("/user/ai/chat")
@router.post("/ai/chat")
async def chat(
    payload: AiChatIn,
    request: Request,
    stream: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """发送 AI 消息；默认返回 SSE，显式关闭流式时返回 HTTP 201 JSON。"""

    ip_address = client_ip(request)
    if not _should_stream(stream, payload.stream):
        return created(
            await ai_service.chat(
                db,
                user=current_user,
                conversation_id=payload.conversation_id,
                message=payload.message,
                ip_address=ip_address,
            ),
            "AI 回复成功",
        )
    return StreamingResponse(
        _stream_events(
            db,
            user=current_user,
            payload=payload,
            ip_address=ip_address,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/user/ai/conversations")
@router.post("/ai/conversations")
async def create_conversation(
    payload: AiConversationCreateIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """创建一个空 AI 会话，并返回前端可立即选中的会话对象。"""

    return created(
        await ai_service.create_conversation(
            db,
            user=current_user,
            title=payload.title,
            ip_address=client_ip(request),
        ),
        "AI 会话创建成功",
    )


@router.get("/user/ai/conversations")
@router.get("/ai/conversations")
async def conversations(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """按最近活动时间返回当前用户的有效 AI 会话列表。"""

    return api_response(
        await ai_service.list_conversations(db, user_id=current_user.id)
    )


@router.get("/user/ai/conversations/{conversation_id}/messages")
@router.get("/ai/conversations/{conversation_id}/messages")
async def messages(
    conversation_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """返回指定自有会话的消息和仍公开的推荐图片详情。"""

    return api_response(
        await ai_service.list_messages(
            db,
            user_id=current_user.id,
            conversation_id=conversation_id,
        )
    )


@router.delete("/user/ai/conversations/{conversation_id}")
@router.delete("/ai/conversations/{conversation_id}")
async def remove_conversation(
    conversation_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """软删除一条自有会话及其全部有效消息。"""

    return api_response(
        await ai_service.delete_conversation(
            db,
            user=current_user,
            conversation_id=conversation_id,
            ip_address=client_ip(request),
        ),
        "AI 会话已删除",
    )


@router.delete("/user/ai/conversations")
@router.delete("/ai/conversations")
async def clear_conversations(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """软删除当前用户的全部 AI 会话及消息。"""

    return api_response(
        await ai_service.clear_conversations(db, user_id=current_user.id),
        "AI 会话已清空",
    )
