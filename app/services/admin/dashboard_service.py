"""管理后台总览指标聚合与审计日志分页查询。"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin_log import AdminLog
from app.models.ai import AiConversation
from app.models.image import Image
from app.models.user import User
from app.utils.pagination import normalize_pagination, pagination_payload


def _serialize_log(log: AdminLog) -> dict:
    """输出前端日志表格使用的稳定 snake_case 字段。"""

    return {
        "id": log.id,
        "actor_id": log.actor_id,
        "actor_name": log.actor_name,
        "actor_role": log.actor_role,
        "action_type": log.action_type,
        "target_type": log.target_type,
        "target_id": log.target_id,
        "title": log.title,
        "content": log.content,
        "ip_address": log.ip_address,
        "created_at": log.created_at,
    }


async def dashboard_stats(db: AsyncSession) -> dict:
    """聚合未删除图片、用户、行为计数和有效 AI 会话数。"""

    image_conditions = [Image.deleted_at.is_(None), Image.status != "deleted"]
    image_count = await db.scalar(select(func.count()).select_from(Image).where(*image_conditions))
    user_count = await db.scalar(select(func.count()).select_from(User).where(User.deleted_at.is_(None)))
    totals = (
        await db.execute(
            select(
                func.coalesce(func.sum(Image.view_count), 0),
                func.coalesce(func.sum(Image.download_count), 0),
                func.coalesce(func.sum(Image.favorite_count), 0),
            ).where(Image.deleted_at.is_(None))
        )
    ).one()
    conversation_count = await db.scalar(
        select(func.count()).select_from(AiConversation).where(AiConversation.deleted_at.is_(None))
    )
    return {
        "image_count": image_count or 0,
        "user_count": user_count or 0,
        "total_view_count": totals[0] or 0,
        "total_download_count": totals[1] or 0,
        "total_favorite_count": totals[2] or 0,
        "ai_conversation_count": conversation_count or 0,
    }


async def list_logs(
    db: AsyncSession,
    *,
    page: int,
    page_size: int,
    action_type: str | None,
    target_type: str | None,
) -> dict:
    """按行为/目标类型筛选日志并返回标准分页结构。"""

    page, page_size, offset = normalize_pagination(page, page_size)
    conditions = []
    if action_type:
        conditions.append(AdminLog.action_type == action_type)
    if target_type:
        conditions.append(AdminLog.target_type == target_type)
    total = await db.scalar(select(func.count()).select_from(AdminLog).where(*conditions)) or 0
    logs = list(
        (
            await db.scalars(
                select(AdminLog)
                .where(*conditions)
                .order_by(AdminLog.created_at.desc(), AdminLog.id.desc())
                .offset(offset)
                .limit(page_size)
            )
        ).all()
    )
    return {
        "list": [_serialize_log(log) for log in logs],
        "pagination": pagination_payload(
            page=page,
            page_size=page_size,
            total=total,
        ),
    }
