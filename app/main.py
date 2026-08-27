"""FastAPI 应用入口。

创建应用实例，注册跨域、统一异常、业务路由、上传目录和健康检查端点。
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.router import register_api_routes
from app.core.config import settings
from app.core.exceptions import register_exception_handlers

app = FastAPI(title="Taoling Gallery API", version="1.0.0")

# Vue 开发服务器通过 8000 端口跨域请求，并携带登录 Cookie。
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)
register_api_routes(app)
app.mount(
    "/uploads",
    StaticFiles(directory=settings.upload_path, check_dir=False),
    name="uploads",
)


@app.get("/health")
async def health():
    """返回负载均衡、部署脚本和监控使用的服务探活结果。"""

    return {"code": 200, "message": "success", "data": {"status": "ok"}}
