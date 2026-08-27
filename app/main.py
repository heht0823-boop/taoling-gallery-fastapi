"""
应用入口模块。

创建 FastAPI 应用实例，注册全局异常处理器，并定义健康检查接口。
"""
from fastapi import FastAPI

from app.api.router import api_router
from app.core.exceptions import register_exception_handlers

# 创建 FastAPI 应用实例，配置应用标题与版本号
app=FastAPI(
    title='Taoling Gallery API',  # 应用名称，展示在 Swagger 文档标题
    version='1.0.0'               # 接口版本号
)
# 注册全局异常处理器，统一所有异常返回格式为 {code, message, data}
register_exception_handlers(app)
app.include_router(api_router)
@app.get('/health')
async def health():
    """健康检查接口：用于探活（负载均衡、部署脚本），返回服务运行状态。"""
    return {
        'code':200,
        'message':'success',
        'data':{"status":"ok"}
    }