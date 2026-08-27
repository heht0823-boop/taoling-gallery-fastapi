from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_user
from app.core.database import get_db
from app.core.response import api_response
from app.models.user import User
from app.schemas.profile import PasswordUpdateIn, ProfileUpdateIn
from app.services import auth_service, profile_service

router = APIRouter(prefix="/user", tags=["user-profile"])


@router.get("/profile")
@router.get("/profile/summary")
async def profile_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    return api_response(await auth_service.get_user_with_stats(db, current_user.id))


@router.put("/profile")
@router.patch("/profile")
async def update_profile(
    payload: ProfileUpdateIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    return api_response(
        await profile_service.update_profile(
            db,
            user_id=current_user.id,
            updates=payload.model_dump(exclude_unset=True),
            ip_address=request.client.host if request.client else None,
        ),
        "资料修改成功",
    )


@router.patch("/password")
async def update_password(
    payload: PasswordUpdateIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    return api_response(
        await profile_service.update_password(
            db,
            user_id=current_user.id,
            old_password=payload.old_password,
            new_password=payload.new_password,
            ip_address=request.client.host if request.client else None,
        ),
        "密码修改成功",
    )
