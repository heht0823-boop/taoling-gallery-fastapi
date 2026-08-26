from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class WeatherLiveCache(Base):
    __tablename__ = "weather_live_cache"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    adcode: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    city: Mapped[str | None] = mapped_column(String(100))
    province: Mapped[str | None] = mapped_column(String(100))
    weather: Mapped[str | None] = mapped_column(String(100))
    temperature: Mapped[str | None] = mapped_column(String(32))
    winddirection: Mapped[str | None] = mapped_column(String(32))
    windpower: Mapped[str | None] = mapped_column(String(32))
    humidity: Mapped[str | None] = mapped_column(String(32))
    report_time: Mapped[str | None] = mapped_column(String(64))
    source: Mapped[str | None] = mapped_column(String(32))
    raw_payload: Mapped[dict | None] = mapped_column(JSON)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now, onupdate=datetime.now
    )


class WeatherForecastCache(Base):
    __tablename__ = "weather_forecast_cache"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    adcode: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    city: Mapped[str | None] = mapped_column(String(100))
    province: Mapped[str | None] = mapped_column(String(100))
    report_time: Mapped[str | None] = mapped_column(String(64))
    casts: Mapped[list | None] = mapped_column(JSON)
    source: Mapped[str | None] = mapped_column(String(32))
    raw_payload: Mapped[dict | None] = mapped_column(JSON)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now, onupdate=datetime.now
    )
