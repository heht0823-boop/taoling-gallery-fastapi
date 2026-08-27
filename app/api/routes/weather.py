"""天气公开路由。

路径和 query 参数保持 Node/Express 版本：``city`` 使用高德 adcode，批量接口
使用逗号分隔的 ``cities``，``refresh=true`` 可强制刷新第三方缓存。
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import bad_request
from app.core.response import api_response
from app.services import weather_service

router = APIRouter(prefix="/weather", tags=["weather"])


def _force_refresh(value: str | None) -> bool:
    """兼容浏览器 query string 中常见的真值写法。"""

    return str(value or "").lower() in {"1", "true", "yes"}


def _require_city(city: str | None) -> str:
    """集中校验 city，确保缺参文案与原 Node 控制器保持一致。"""

    if not city or not city.strip():
        raise bad_request("缺少 city 参数（城市编码 adcode）")
    return city.strip()


@router.get("/live")
async def live_weather(
    city: str | None = None,
    refresh: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """返回指定城市的实况天气和缓存状态。"""

    return api_response(
        await weather_service.get_live_weather(
            db,
            city=_require_city(city),
            refresh=_force_refresh(refresh),
        ),
        "获取实况天气成功",
    )


@router.get("/live/batch")
async def batch_live_weather(
    cities: str | None = None,
    refresh: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """解析逗号分隔的城市编码并保持原有顺序批量查询。"""

    if not cities:
        raise bad_request("缺少 cities 参数（城市编码列表，逗号分隔）")
    city_list = [item.strip() for item in cities.split(",") if item.strip()]
    if not city_list:
        raise bad_request("cities 参数格式错误，请提供有效的城市编码")
    return api_response(
        await weather_service.get_batch_live_weather(
            db,
            cities=city_list,
            refresh=_force_refresh(refresh),
        ),
        "批量获取实况天气成功",
    )


@router.get("/forecast")
async def forecast_weather(
    city: str | None = None,
    refresh: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """返回指定城市的多日天气预报。"""

    return api_response(
        await weather_service.get_forecast_weather(
            db,
            city=_require_city(city),
            refresh=_force_refresh(refresh),
        ),
        "获取天气预报成功",
    )


@router.get("/24h")
async def hourly_trend(
    city: str | None = None,
    refresh: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """返回前端温度趋势图使用的 24 小时数据。"""

    return api_response(
        await weather_service.get_hourly_trend(
            db,
            city=_require_city(city),
            refresh=_force_refresh(refresh),
        ),
        "获取 24 小时趋势成功",
    )


@router.get("/warnings")
async def warnings(city: str | None = None):
    """返回指定城市或全部城市的气象预警列表。"""

    message = "获取气象预警成功" if city else "获取全部气象预警成功"
    return api_response(weather_service.get_warnings(city), message)


@router.get("/tips")
async def life_tips(city: str | None = Query(default=None)):
    """返回指定城市的六项生活指数建议。"""

    return api_response(
        weather_service.get_life_tips(_require_city(city)),
        "获取生活指数成功",
    )
