from datetime import datetime, timedelta

from app.services.weather_service import is_fresh


def test_weather_cache_freshness_honors_ttl_boundary():
    now = datetime(2026, 8, 27, 12, 0, 0)

    assert is_fresh(now - timedelta(minutes=29), 30, now=now) is True
    assert is_fresh(now - timedelta(minutes=31), 30, now=now) is False
