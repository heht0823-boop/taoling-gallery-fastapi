"""应用 API 子路由的集中注册入口。

FastAPI 0.141 会把 ``APIRouter.include_router`` 保存为惰性包含项；如果再把该
聚合路由挂到应用，接口虽然能够匹配请求，却不会完整进入 OpenAPI。这里直接
把叶子路由注册到应用，确保运行时路由和接口文档使用同一份清单。
"""

from fastapi import APIRouter, FastAPI

from app.api.routes.admin.categories import router as admin_categories_router
from app.api.routes.admin.dashboard import router as admin_dashboard_router
from app.api.routes.admin.images import router as admin_images_router
from app.api.routes.admin.messages import router as admin_messages_router
from app.api.routes.admin.tags import router as admin_tags_router
from app.api.routes.admin.users import router as admin_users_router
from app.api.routes.auth import router as auth_router
from app.api.routes.public import router as public_router
from app.api.routes.user.downloads import router as user_downloads_router
from app.api.routes.user.favorites import router as user_favorites_router
from app.api.routes.user.messages import router as user_messages_router
from app.api.routes.user.profile import router as user_profile_router
from app.api.routes.weather import router as weather_router

API_PREFIX = "/api"

# 注册顺序与原 Express ``routes/index.js`` 保持一致，便于逐项核对接口契约。
API_ROUTERS: tuple[APIRouter, ...] = (
    auth_router,
    public_router,
    user_profile_router,
    user_favorites_router,
    user_downloads_router,
    user_messages_router,
    weather_router,
    admin_dashboard_router,
    admin_images_router,
    admin_categories_router,
    admin_tags_router,
    admin_users_router,
    admin_messages_router,
)


def register_api_routes(app: FastAPI) -> None:
    """把全部叶子路由直接挂到应用的 ``/api`` 前缀下。"""

    for router in API_ROUTERS:
        app.include_router(router, prefix=API_PREFIX)
