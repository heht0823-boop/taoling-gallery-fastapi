from fastapi import APIRouter

from app.api.routes.admin.categories import router as admin_categories_router
from app.api.routes.admin.dashboard import router as admin_dashboard_router
from app.api.routes.admin.images import router as admin_images_router
from app.api.routes.admin.messages import router as admin_messages_router
from app.api.routes.admin.tags import router as admin_tags_router
from app.api.routes.admin.users import router as admin_users_router

# 导入auth模块路由实例，别名 auth_router
from app.api.routes.auth import router as auth_router
from app.api.routes.public import router as public_router
from app.api.routes.user.downloads import router as user_downloads_router
from app.api.routes.user.favorites import router as user_favorites_router
from app.api.routes.user.messages import router as user_messages_router
from app.api.routes.user.profile import router as user_profile_router
from app.api.routes.weather import router as weather_router

# 创建总API路由对象，统一添加 /api 全局前缀
# 所有通过 api_router 挂载的子路由，URL都会带上 /api
api_router = APIRouter(prefix="/api")

# 将认证模块路由注册到总路由下
# auth_router自身prefix="/auth"，拼接后完整路径：/api/auth/xxx
api_router.include_router(auth_router)
api_router.include_router(public_router)
api_router.include_router(user_downloads_router)
api_router.include_router(user_favorites_router)
api_router.include_router(user_messages_router)
api_router.include_router(user_profile_router)
api_router.include_router(admin_dashboard_router)
api_router.include_router(admin_images_router)
api_router.include_router(admin_categories_router)
api_router.include_router(admin_tags_router)
api_router.include_router(admin_users_router)
api_router.include_router(admin_messages_router)
api_router.include_router(weather_router)
