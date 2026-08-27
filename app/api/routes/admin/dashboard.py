"""管理后台总览统计与管理员操作日志查询路由。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.core.database import get_db
from app.core.response import api_response
from app.models.user import User
from app.services.admin import dashboard_service

router = APIRouter(prefix="/admin", tags=["admin-dashboard"])


@router.get("/dashboard/stats")
async def dashboard_stats(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """返回管理首页六项固定统计指标。"""

    return api_response(await dashboard_service.dashboard_stats(db))


@router.get("/logs")
async def logs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=12, alias="pageSize", ge=1, le=100),
    action_type: str | None = None,
    target_type: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """按行为类型和目标类型筛选管理员日志。"""

    return api_response(
        await dashboard_service.list_logs(
            db,
            page=page,
            page_size=page_size,
            action_type=action_type,
            target_type=target_type,
        )
    )
