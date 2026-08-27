"""
图片模块数据模型。

定义图片库的核心表：分类（Category）、标签（Tag）、
图片（Image）以及图片-标签多对多关联表（ImageTag）。
"""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, Text
from sqlalchemy.dialects.mysql import ENUM
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Category(Base):
    """图片分类表：对图片做一级归类，如“风景”“动漫”“插画”等。"""

    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # 主键ID
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)  # 分类名称，全局唯一
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 排序权重，数字越小越靠前
    # 状态：normal启用 / disabled停用
    status: Mapped[str] = mapped_column(
        ENUM("normal", "disabled"), nullable=False, default="normal"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)  # 创建时间
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now, onupdate=datetime.now  # 更新时间，修改自动刷新
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime)  # 软删除时间，为空表示未删除


class Tag(Base):
    """标签表：图片的细粒度标记，一张图可挂多个标签，支持颜色与引用计数。"""

    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # 主键ID
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)  # 标签名称，全局唯一
    color: Mapped[str | None] = mapped_column(String(32))  # 标签展示颜色（十六进制色值）
    usage_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 被图片引用的次数
    # 状态：normal启用 / disabled停用
    status: Mapped[str] = mapped_column(
        ENUM("normal", "disabled"), nullable=False, default="normal"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)  # 创建时间
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now, onupdate=datetime.now  # 更新时间，修改自动刷新
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime)  # 软删除时间，为空表示未删除


class Image(Base):
    """图片表：图片库核心资源，含图片地址、分类归属、可见状态与各项行为计数。"""

    __tablename__ = "images"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # 主键ID
    title: Mapped[str] = mapped_column(String(200), nullable=False)  # 图片标题
    description: Mapped[str | None] = mapped_column(Text)  # 图片描述/简介
    image_url: Mapped[str] = mapped_column(String(500), nullable=False)  # 原图访问地址
    thumbnail_url: Mapped[str | None] = mapped_column(String(500))  # 缩略图地址，列表页使用
    category_id: Mapped[int | None] = mapped_column(BigInteger)  # 所属分类ID，关联categories表，可为空
    aspect_ratio: Mapped[str | None] = mapped_column(String(20))  # 宽高比（如 "16:9"），供前端布局使用
    status: Mapped[str] = mapped_column(
        # 可见状态：public公开 / private私有 / draft草稿 / deleted已删除
        ENUM("public", "private", "draft", "deleted"),
        nullable=False,
        default="draft",
    )
    # 展示权重，越大越靠前（置顶）
    display_weight: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    view_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 浏览次数
    download_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 下载次数
    favorite_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 收藏次数
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)  # 创建时间
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now, onupdate=datetime.now  # 更新时间，修改自动刷新
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime)  # 软删除时间，为空表示未删除


class ImageTag(Base):
    """图片-标签关联表：多对多关系的中间表，记录每张图片挂了哪些标签。"""

    __tablename__ = "image_tags"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # 主键ID
    image_id: Mapped[int] = mapped_column(BigInteger, nullable=False)  # 图片ID，关联images表
    tag_id: Mapped[int] = mapped_column(BigInteger, nullable=False)  # 标签ID，关联tags表
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)  # 绑定时间
