"""
天气模块数据模型。

缓存高德地图天气接口的实时天气与天气预报数据，
避免每次请求都调用第三方接口（受接口限流与稳定性约束）。
"""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class WeatherLiveCache(Base):
    """实时天气缓存表：按行政区划编码（adcode）缓存一条最新实时天气。"""

    __tablename__ = "weather_live_cache"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # 主键ID
    # 行政区划编码，唯一（一个城市一条缓存）
    adcode: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    city: Mapped[str | None] = mapped_column(String(100))  # 城市名称
    province: Mapped[str | None] = mapped_column(String(100))  # 省份名称
    weather: Mapped[str | None] = mapped_column(String(100))  # 天气现象（晴/多云/雨等）
    temperature: Mapped[str | None] = mapped_column(String(32))  # 实时温度（单位：℃）
    winddirection: Mapped[str | None] = mapped_column(String(32))  # 风向
    windpower: Mapped[str | None] = mapped_column(String(32))  # 风力等级
    humidity: Mapped[str | None] = mapped_column(String(32))  # 相对湿度（%）
    report_time: Mapped[str | None] = mapped_column(String(64))  # 气象台发布时间（接口原始字符串）
    source: Mapped[str | None] = mapped_column(String(32))  # 数据来源标识（如 amap）
    raw_payload: Mapped[dict | None] = mapped_column(JSON)  # 接口原始返回JSON，便于排查与扩展
    fetched_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)  # 拉取时间，用于判断缓存是否过期
    # 记录创建时间
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now, onupdate=datetime.now  # 更新时间，修改自动刷新
    )


class WeatherForecastCache(Base):
    """天气预报缓存表：按行政区划编码缓存未来数日的天气预报。"""

    __tablename__ = "weather_forecast_cache"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # 主键ID
    adcode: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)  # 行政区划编码，唯一
    city: Mapped[str | None] = mapped_column(String(100))  # 城市名称
    province: Mapped[str | None] = mapped_column(String(100))  # 省份名称
    report_time: Mapped[str | None] = mapped_column(String(64))  # 气象台发布时间（接口原始字符串）
    casts: Mapped[list | None] = mapped_column(JSON)  # 逐日预报列表（日期/天气/温度等组成的数组）
    source: Mapped[str | None] = mapped_column(String(32))  # 数据来源标识（如 amap）
    raw_payload: Mapped[dict | None] = mapped_column(JSON)  # 接口原始返回JSON
    fetched_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)  # 拉取时间，用于判断缓存是否过期
    # 记录创建时间
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now, onupdate=datetime.now  # 更新时间，修改自动刷新
    )
