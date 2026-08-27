"""个人中心资料、头像与密码路由。

头像接口同时接受 multipart 文件和 JSON 远程地址，以兼容前端历史调用方式；
资料与密码修改继续使用统一 Cookie 鉴权和统一响应包络。
"""

from fastapi import APIRouter, Depends, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.api.deps import require_user
from app.core.database import get_db
from app.core.response import api_response
from app.models.user import User
from app.schemas.profile import PasswordUpdateIn, ProfileUpdateIn
from app.services import auth_service, avatar_service, profile_service

router = APIRouter(prefix="/user", tags=["user-profile"])


@router.get("/profile")
@router.get("/profile/summary")
async def profile_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """返回当前用户资料及行为统计汇总。"""

    return api_response(await auth_service.get_user_with_stats(db, current_user.id))


@router.put("/profile")
@router.patch("/profile")
async def update_profile(
    payload: ProfileUpdateIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """修改用户名/邮箱/简介等可编辑资料。"""

    return api_response(
        await profile_service.update_profile(
            db,
            user_id=current_user.id,
            updates=payload.model_dump(exclude_unset=True),
            ip_address=request.client.host if request.client else None,
        ),
        "资料修改成功",
    )


async def _read_avatar_input(request: Request) -> tuple[UploadFile | None, str | None]:
    """根据 Content-Type 读取 multipart 文件或 JSON 远程头像地址。"""

    content_type = request.headers.get("content-type", "").lower()
    if content_type.startswith("multipart/form-data"):
        form = await request.form()
        file = form.get("file")
        avatar_url = form.get("avatar_url")
        return (
            file if isinstance(file, StarletteUploadFile) else None,
            str(avatar_url) if avatar_url else None,
        )
    try:
        payload = await request.json()
    except ValueError:
        return None, None
    if not isinstance(payload, dict):
        return None, None
    avatar_url = payload.get("avatar_url") or payload.get("avatarUrl")
    return None, str(avatar_url) if avatar_url else None


@router.post("/profile/avatar")
@router.patch("/profile/avatar")
async def update_avatar(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """保存新头像并在数据库失败时清理刚生成的文件。"""

    file, remote_url = await _read_avatar_input(request)
    asset = await avatar_service.store_avatar(file=file, remote_url=remote_url)
    try:
        result = await profile_service.update_avatar(
            db,
            user_id=current_user.id,
            asset=asset,
            ip_address=request.client.host if request.client else None,
        )
    except Exception:
        avatar_service.remove_avatar_asset(asset)
        raise
    return api_response(result, "头像修改成功")


@router.patch("/password")
async def update_password(
    payload: PasswordUpdateIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """校验旧密码后替换密码哈希。"""

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
