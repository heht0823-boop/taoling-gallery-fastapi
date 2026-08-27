from fastapi import APIRouter

# 导入auth模块路由实例，别名 auth_router
from app.api.routes.auth import router as auth_router
from app.api.routes.public import router as public_router
from app.api.routes.user.favorites import router as user_favorites_router

# 创建总API路由对象，统一添加 /api 全局前缀
# 所有通过 api_router 挂载的子路由，URL都会带上 /api
api_router = APIRouter(prefix="/api")

# 将认证模块路由注册到总路由下
# auth_router自身prefix="/auth"，拼接后完整路径：/api/auth/xxx
api_router.include_router(auth_router)
api_router.include_router(public_router)
api_router.include_router(user_favorites_router)
