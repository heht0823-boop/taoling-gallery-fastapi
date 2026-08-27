"""高德天气 HTTP 客户端。

本模块只负责第三方请求和协议级错误转换，不写数据库，也不决定缓存策略。
这样天气业务服务可以在单元测试中替换该函数，而不会访问真实外网。
"""

import httpx

from app.core.config import settings
from app.core.exceptions import AppError

AMAP_WEATHER_URL = "https://restapi.amap.com/v3/weather/weatherInfo"


async def fetch_amap(city: str, *, extensions: str) -> dict:
    """按行政区划编码调用高德天气接口并返回原始 JSON。

    ``extensions`` 必须由业务层传入 ``base``（实况）或 ``all``（预报）。
    第三方超时、HTTP 异常和业务失败统一转换为 ``AppError``，防止高德响应
    结构直接泄漏给前端，同时给陈旧缓存降级逻辑留下明确的失败原因。
    """

    if not settings.amap_key:
        raise AppError(503, "AMAP_KEY 未配置")
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.get(
                AMAP_WEATHER_URL,
                params={
                    "key": settings.amap_key,
                    "city": city,
                    "extensions": extensions,
                    "output": "JSON",
                },
            )
            response.raise_for_status()
            payload = response.json()
    except httpx.TimeoutException as exc:
        raise AppError(504, "高德天气请求超时") from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise AppError(502, "高德天气请求失败") from exc
    if payload.get("status") != "1":
        raise AppError(502, payload.get("info") or "高德天气请求失败")
    return payload
