from fastapi import FastAPI
from app.core.exceptions import register_exception_handlers

app=FastAPI(
    title='Taoling Gallery API',
    version='1.0.0'
)
# 注册异常处理程序
register_exception_handlers(app)
@app.get('/health')
async def health():
    return {
        'code':200,
        'message':'success',
        'data':{"status":"ok"}
    }