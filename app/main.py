from fastapi import FastAPI
app=FastAPI(
    title='Taoling Gallery API',
    version='1.0.0'
)
@app.get('/health')
async def health():
    return {
        'code':200,
        'message':'success',
        'data':{"status":"ok"}
    }