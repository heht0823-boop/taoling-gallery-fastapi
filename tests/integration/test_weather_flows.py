from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.core.exceptions import AppError
from app.main import app
from app.models.weather import WeatherForecastCache, WeatherLiveCache


@pytest.fixture
async def weather_records(gallery_records):
    """在现有回滚事务内准备一组实况与预报缓存，测试后不留下数据。"""

    db, *_ = gallery_records
    adcode = f"9{uuid4().int % 100000:05d}"
    now = datetime.now()
    live = WeatherLiveCache(
        adcode=adcode,
        city="测试市",
        province="测试省",
        weather="晴",
        temperature="26",
        winddirection="东",
        windpower="2",
        humidity="55",
        report_time="2026-08-27 12:00:00",
        source="amap",
        raw_payload={},
        fetched_at=now,
    )
    forecast = WeatherForecastCache(
        adcode=adcode,
        city="测试市",
        province="测试省",
        report_time="2026-08-27 11:00:00",
        casts=[
            {
                "date": "2026-08-27",
                "week": "4",
                "dayweather": "晴",
                "nightweather": "多云",
                "daytemp": "31",
                "nighttemp": "22",
                "daywind": "东",
                "nightwind": "东",
                "daypower": "2",
                "nightpower": "2",
            }
        ],
        source="amap",
        raw_payload={},
        fetched_at=now,
    )
    db.add_all([live, forecast])
    await db.flush()
    return db, live, forecast


@pytest.fixture
async def weather_client(weather_records):
    db, *_ = weather_records

    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)


async def test_live_weather_uses_cache_and_exact_frontend_fields(
    weather_client,
    weather_records,
):
    _, live, _ = weather_records

    response = await weather_client.get(
        "/api/weather/live",
        params={"city": live.adcode},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["message"] == "获取实况天气成功"
    assert set(payload["data"]) == {
        "temperature",
        "weather",
        "winddirection",
        "windpower",
        "humidity",
        "adcode",
        "province",
        "city",
        "reportTime",
        "source",
        "cacheStatus",
        "cachedAt",
        "cacheExpiresAt",
    }
    assert payload["data"]["cacheStatus"] == "cache"
    assert payload["data"]["reportTime"] == "2026-08-27 12:00:00"


async def test_live_weather_refreshes_provider_and_persists_cache(
    weather_client,
    weather_records,
    monkeypatch,
):
    db, live, _ = weather_records

    async def fake_fetch(city: str, *, extensions: str):
        assert city == live.adcode
        assert extensions == "base"
        return {
            "status": "1",
            "lives": [
                {
                    "adcode": city,
                    "city": "更新市",
                    "province": "更新省",
                    "weather": "小雨",
                    "temperature": "19",
                    "winddirection": "北",
                    "windpower": "3",
                    "humidity": "80",
                    "reporttime": "2026-08-27 13:00:00",
                }
            ],
        }

    monkeypatch.setattr("app.services.weather_provider.fetch_amap", fake_fetch)
    response = await weather_client.get(
        "/api/weather/live",
        params={"city": live.adcode, "refresh": "true"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["cacheStatus"] == "refreshed"
    assert response.json()["data"]["weather"] == "小雨"
    await db.refresh(live)
    assert live.city == "更新市"
    assert live.temperature == "19"


async def test_provider_failure_uses_stale_cache_or_returns_503(
    weather_client,
    weather_records,
    monkeypatch,
):
    db, live, _ = weather_records
    live.fetched_at = datetime.now() - timedelta(days=1)
    await db.flush()

    async def failed_fetch(city: str, *, extensions: str):
        raise AppError(502, "上游服务失败")

    monkeypatch.setattr("app.services.weather_provider.fetch_amap", failed_fetch)
    stale = await weather_client.get(
        "/api/weather/live",
        params={"city": live.adcode},
    )
    unavailable = await weather_client.get(
        "/api/weather/live",
        params={"city": "100000"},
    )

    assert stale.status_code == 200
    assert stale.json()["data"]["cacheStatus"] == "stale"
    assert stale.json()["data"]["fallbackReason"] == "上游服务失败"
    assert unavailable.status_code == 503
    assert unavailable.json() == {
        "code": 503,
        "message": "天气服务暂时不可用",
        "data": {},
    }


async def test_forecast_hourly_warnings_and_tips_match_vue_contract(
    weather_client,
    weather_records,
):
    _, live, _ = weather_records
    forecast = await weather_client.get(
        "/api/weather/forecast",
        params={"city": live.adcode},
    )
    hourly = await weather_client.get(
        "/api/weather/24h",
        params={"city": live.adcode},
    )
    warnings = await weather_client.get(
        "/api/weather/warnings",
        params={"city": live.adcode},
    )
    tips = await weather_client.get(
        "/api/weather/tips",
        params={"city": live.adcode},
    )

    forecast_data = forecast.json()["data"]
    assert set(forecast_data) == {
        "city",
        "adcode",
        "province",
        "reportTime",
        "casts",
        "source",
        "cacheStatus",
        "cachedAt",
        "cacheExpiresAt",
    }
    assert set(forecast_data["casts"][0]) == {
        "date",
        "week",
        "dayweather",
        "nightweather",
        "daytemp",
        "nighttemp",
        "daywind",
        "nightwind",
        "daypower",
        "nightpower",
    }
    assert len(hourly.json()["data"]) == 24
    assert all(
        set(item) == {"time", "temperature", "weather"} and isinstance(item["temperature"], int)
        for item in hourly.json()["data"]
    )
    assert warnings.json()["data"] == []
    assert set(tips.json()["data"]) == {
        "uv",
        "dressing",
        "carWash",
        "sport",
        "travel",
        "coldRisk",
    }


async def test_weather_query_validation_keeps_node_error_envelope(weather_client):
    live = await weather_client.get("/api/weather/live")
    batch = await weather_client.get("/api/weather/live/batch")

    assert live.status_code == 400
    assert live.json()["message"] == "缺少 city 参数（城市编码 adcode）"
    assert batch.status_code == 400
    assert batch.json()["message"] == "缺少 cities 参数（城市编码列表，逗号分隔）"
