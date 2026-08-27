"""
用户行为模块数据模型。

记录用户对图片的收藏、下载、浏览行为明细，
用于个人中心展示与运营统计分析。
"""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Favorite(Base):
    """收藏表：用户收藏图片的记录，一个用户可收藏多张图片。"""

    __tablename__ = "favorites"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # 主键ID
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)  # 收藏用户ID，关联users表
    image_id: Mapped[int] = mapped_column(BigInteger, nullable=False)  # 被收藏图片ID，关联images表
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)  # 收藏时间


class DownloadRecord(Base):
    """下载记录表：记录用户下载图片的行为，保留当时的图片快照信息。"""

    __tablename__ = "download_records"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # 主键ID
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)  # 下载用户ID，关联users表
    image_id: Mapped[int] = mapped_column(BigInteger, nullable=False)  # 被下载图片ID，关联images表
    # 图片标题快照（图片改名后仍可追溯）
    image_title: Mapped[str] = mapped_column(String(200), nullable=False)
    image_url: Mapped[str] = mapped_column(String(500), nullable=False)  # 图片地址快照
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)  # 下载时间
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime)  # 软删除时间，为空表示未删除


class ImageViewRecord(Base):
    """图片浏览记录表：记录每次图片浏览行为，登录用户与游客均会记录。"""

    __tablename__ = "image_view_records"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # 主键ID
    user_id: Mapped[int | None] = mapped_column(BigInteger)  # 登录用户ID，游客为空
    image_id: Mapped[int] = mapped_column(BigInteger, nullable=False)  # 被浏览图片ID，关联images表
    visitor_id: Mapped[str | None] = mapped_column(String(100))  # 游客标识（浏览器生成的匿名ID）
    image_title: Mapped[str | None] = mapped_column(String(200))  # 图片标题快照
    ip_address: Mapped[str | None] = mapped_column(String(64))  # 访问者IP地址
    user_agent: Mapped[str | None] = mapped_column(String(500))  # 访问者浏览器 UA 标识
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)  # 浏览时间
