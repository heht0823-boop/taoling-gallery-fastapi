"""天气缓存、字段适配与降级策略。

对外返回字段严格沿用原 Vue 前端的 ``LiveWeather`` / ``ForecastWeather``
类型；数据库字段保持 snake_case，仅在序列化边界转换 ``reportTime``、
``cacheStatus`` 等驼峰字段。
"""

import math
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppError
from app.models.weather import WeatherForecastCache, WeatherLiveCache
from app.services import weather_provider


def is_fresh(
    fetched_at: datetime,
    ttl_minutes: int,
    *,
    now: datetime | None = None,
) -> bool:
    """判断缓存拉取时间是否仍处于配置的有效期内。"""

    current = now or datetime.now()
    return fetched_at >= current - timedelta(minutes=ttl_minutes)


def _format_datetime(value: datetime | str | None) -> str:
    """把数据库时间转换成前端约定的本地时间字符串。"""

    if not value:
        return ""
    if isinstance(value, str):
        return value
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _failure_reason(exc: Exception) -> str:
    """提取可向前端展示的天气服务降级原因。"""

    if isinstance(exc, AppError):
        return exc.message
    return "天气服务暂时不可用"


def _cache_meta(fetched_at: datetime, ttl_minutes: int, status: str) -> dict:
    """构造天气响应统一使用的缓存状态字段。"""

    return {
        "cacheStatus": status,
        "cachedAt": _format_datetime(fetched_at),
        "cacheExpiresAt": _format_datetime(fetched_at + timedelta(minutes=ttl_minutes)),
    }


def serialize_live(
    cache: WeatherLiveCache,
    *,
    cache_status: str,
    fallback_reason: str | None = None,
) -> dict:
    """把实时缓存记录转换为 Vue ``LiveWeather`` 的精确字段形状。"""

    data = {
        "temperature": cache.temperature or "",
        "weather": cache.weather or "",
        "winddirection": cache.winddirection or "",
        "windpower": cache.windpower or "",
        "humidity": cache.humidity or "",
        "adcode": cache.adcode,
        "province": cache.province or "",
        "city": cache.city or "",
        "reportTime": _format_datetime(cache.report_time),
        "source": cache.source or "amap",
        **_cache_meta(
            cache.fetched_at,
            settings.amap_live_cache_minutes,
            cache_status,
        ),
    }
    if fallback_reason:
        data["fallbackReason"] = fallback_reason
    return data


def serialize_forecast(
    cache: WeatherForecastCache,
    *,
    cache_status: str,
    fallback_reason: str | None = None,
) -> dict:
    """把预报缓存记录转换为 Vue ``ForecastWeather`` 的精确字段形状。"""

    data = {
        "city": cache.city or "",
        "adcode": cache.adcode,
        "province": cache.province or "",
        "reportTime": _format_datetime(cache.report_time),
        "casts": cache.casts or [],
        "source": cache.source or "amap",
        **_cache_meta(
            cache.fetched_at,
            settings.amap_forecast_cache_minutes,
            cache_status,
        ),
    }
    if fallback_reason:
        data["fallbackReason"] = fallback_reason
    return data


async def _find_live_cache(
    db: AsyncSession,
    city: str,
) -> WeatherLiveCache | None:
    """按城市 adcode 查询实况天气缓存。"""

    return await db.scalar(select(WeatherLiveCache).where(WeatherLiveCache.adcode == city))


async def _find_forecast_cache(
    db: AsyncSession,
    city: str,
) -> WeatherForecastCache | None:
    """按城市 adcode 查询天气预报缓存。"""

    return await db.scalar(select(WeatherForecastCache).where(WeatherForecastCache.adcode == city))


async def _upsert_live(db: AsyncSession, payload: dict) -> WeatherLiveCache:
    """校验高德实况响应，并按 adcode 原子地更新当前缓存。"""

    lives = payload.get("lives") or []
    if not lives:
        raise AppError(502, "高德未返回该城市实况天气")
    live = lives[0]
    adcode = str(live.get("adcode") or "").strip()
    if not adcode:
        raise AppError(502, "高德实况天气缺少 adcode")
    cache = await db.scalar(select(WeatherLiveCache).where(WeatherLiveCache.adcode == adcode))
    if not cache:
        cache = WeatherLiveCache(adcode=adcode, fetched_at=datetime.now())
        db.add(cache)
    cache.city = live.get("city")
    cache.province = live.get("province")
    cache.weather = live.get("weather")
    cache.temperature = live.get("temperature")
    cache.winddirection = live.get("winddirection")
    cache.windpower = live.get("windpower")
    cache.humidity = live.get("humidity")
    cache.report_time = live.get("reporttime")
    cache.source = "amap"
    cache.raw_payload = payload
    cache.fetched_at = datetime.now()
    await db.commit()
    await db.refresh(cache)
    return cache


async def _upsert_forecast(
    db: AsyncSession,
    payload: dict,
) -> WeatherForecastCache:
    """筛选前端会使用的逐日字段，并按 adcode 更新预报缓存。"""

    forecasts = payload.get("forecasts") or []
    if not forecasts:
        raise AppError(502, "高德未返回该城市预报天气")
    forecast = forecasts[0]
    adcode = str(forecast.get("adcode") or "").strip()
    if not adcode:
        raise AppError(502, "高德预报天气缺少 adcode")
    casts = [
        {
            "date": item.get("date", ""),
            "week": item.get("week", ""),
            "dayweather": item.get("dayweather", ""),
            "nightweather": item.get("nightweather", ""),
            "daytemp": item.get("daytemp", ""),
            "nighttemp": item.get("nighttemp", ""),
            "daywind": item.get("daywind", ""),
            "nightwind": item.get("nightwind", ""),
            "daypower": item.get("daypower", ""),
            "nightpower": item.get("nightpower", ""),
        }
        for item in forecast.get("casts") or []
    ]
    cache = await db.scalar(select(WeatherForecastCache).where(WeatherForecastCache.adcode == adcode))
    if not cache:
        cache = WeatherForecastCache(adcode=adcode, fetched_at=datetime.now())
        db.add(cache)
    cache.city = forecast.get("city")
    cache.province = forecast.get("province")
    cache.report_time = forecast.get("reporttime")
    cache.casts = casts
    cache.source = "amap"
    cache.raw_payload = payload
    cache.fetched_at = datetime.now()
    await db.commit()
    await db.refresh(cache)
    return cache


async def get_live_weather(
    db: AsyncSession,
    *,
    city: str,
    refresh: bool = False,
) -> dict:
    """读取实况天气：新鲜缓存优先，第三方失败时退回已有陈旧缓存。"""

    city = city.strip()
    cache = await _find_live_cache(db, city)
    if cache and not refresh and is_fresh(cache.fetched_at, settings.amap_live_cache_minutes):
        return serialize_live(cache, cache_status="cache")
    try:
        payload = await weather_provider.fetch_amap(city, extensions="base")
        fresh = await _upsert_live(db, payload)
        return serialize_live(fresh, cache_status="refreshed")
    except Exception as exc:
        # 缓存即使过期也比伪造实时天气更可靠；只有完全没有数据才返回 503。
        if cache:
            return serialize_live(
                cache,
                cache_status="stale",
                fallback_reason=_failure_reason(exc),
            )
        raise AppError(503, "天气服务暂时不可用") from exc


async def get_forecast_weather(
    db: AsyncSession,
    *,
    city: str,
    refresh: bool = False,
) -> dict:
    """读取天气预报，并采用与实况接口相同的缓存降级规则。"""

    city = city.strip()
    cache = await _find_forecast_cache(db, city)
    if cache and not refresh and is_fresh(cache.fetched_at, settings.amap_forecast_cache_minutes):
        return serialize_forecast(cache, cache_status="cache")
    try:
        payload = await weather_provider.fetch_amap(city, extensions="all")
        fresh = await _upsert_forecast(db, payload)
        return serialize_forecast(fresh, cache_status="refreshed")
    except Exception as exc:
        if cache:
            return serialize_forecast(
                cache,
                cache_status="stale",
                fallback_reason=_failure_reason(exc),
            )
        raise AppError(503, "天气服务暂时不可用") from exc


async def get_batch_live_weather(
    db: AsyncSession,
    *,
    cities: list[str],
    refresh: bool = False,
) -> list[dict]:
    """按前端传入顺序返回多个城市，保证卡片与城市列表下标对应。"""

    results = []
    for city in cities:
        results.append(await get_live_weather(db, city=city, refresh=refresh))
    return results


def _number(value: object, fallback: float) -> float:
    """容错转换天气数值，失败时使用给定默认值。"""

    try:
        return float(str(value))
    except (TypeError, ValueError):
        return fallback


async def get_hourly_trend(
    db: AsyncSession,
    *,
    city: str,
    refresh: bool = False,
) -> list[dict]:
    """使用实况及当日高低温插值生成前端图表所需的 24 个整点。"""

    live = await get_live_weather(db, city=city, refresh=refresh)
    forecast = await get_forecast_weather(db, city=city, refresh=refresh)
    first_cast = (forecast.get("casts") or [{}])[0]
    live_temperature = _number(live.get("temperature"), 25)
    day_max = _number(first_cast.get("daytemp"), live_temperature + 3)
    night_min = _number(first_cast.get("nighttemp"), live_temperature - 3)
    now = datetime.now()
    midpoint = (day_max + night_min) / 2
    result = []
    for offset in range(24):
        hour = (now + timedelta(hours=offset)).hour
        cycle_hour = (hour - 14 + 24) % 24
        ratio = math.cos((cycle_hour / 24) * 2 * math.pi)
        temperature = round(midpoint + ((day_max - night_min) / 2) * ratio)
        result.append(
            {
                "time": f"{hour:02d}:00",
                "temperature": temperature,
                "weather": (
                    live.get("weather", "") if offset == 0 else ("晴" if temperature > midpoint else "多云")
                ),
            }
        )
    return result


def get_warnings(city: str | None = None) -> list[dict]:
    """返回气象预警列表；尚无实时预警源时返回类型安全的空数组。"""

    # 不复用 Node 旧项目中过期的静态预警，避免把历史预警展示成当前信息。
    return []


DEFAULT_TIPS = {
    "uv": {"level": "中等", "advice": "涂擦防晒护肤品，避免长时间日晒"},
    "dressing": {"level": "舒适", "advice": "建议穿薄外套或牛仔裤等服装"},
    "carWash": {"level": "适宜", "advice": "天气晴朗，适合洗车"},
    "sport": {"level": "较适宜", "advice": "天气较好，推荐进行户外运动"},
    "travel": {"level": "适宜", "advice": "温度适宜，适合外出游玩"},
    "coldRisk": {"level": "低发", "advice": "感冒几率较低，无需过分担心"},
}


def get_life_tips(city: str) -> dict:
    """返回与前端 ``LifeTips`` 类型完全一致的六项生活建议。"""

    # 返回副本，避免调用方意外修改模块级默认值并污染后续请求。
    return {name: value.copy() for name, value in DEFAULT_TIPS.items()}
