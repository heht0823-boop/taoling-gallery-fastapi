"""
用户模块数据模型。

定义用户主表 User 与用户统计表 UserStat，
覆盖账号信息、角色权限、软删除以及行为统计数据。
"""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String
from sqlalchemy.dialects.mysql import ENUM
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class User(Base):
    """用户表：平台注册用户的基础资料，含账号、角色、状态与登录信息。"""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)  # 主键ID，自增
    username: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)  # 登录用户名，全局唯一
    email: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True)  # 邮箱，可选且唯一
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)  # 密码哈希值，不存明文
    role: Mapped[str] = mapped_column(ENUM("admin", "user"), nullable=False, default="user")  # 角色：admin管理员 / user普通用户
    status: Mapped[str] = mapped_column(ENUM("normal", "disabled"), nullable=False, default="normal")  # 状态：normal正常 / disabled禁用
    avatar_url: Mapped[str | None] = mapped_column(String(500))  # 头像图片URL
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime)  # 最近一次登录时间
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime)  # 软删除时间，为空表示未删除
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)  # 创建时间
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)  # 更新时间，修改自动刷新

    # 一对一关联用户统计表；lazy="selectin" 查询用户时自动带出统计，避免 N+1 问题
    stats: Mapped["UserStat | None"] = relationship(
        primaryjoin="User.id == foreign(UserStat.user_id)",
        back_populates="user",
        uselist=False,
        lazy="selectin",
    )


class UserStat(Base):
    """用户统计表：冗余用户维度的行为计数，避免每次展示都聚合查询明细表。"""

    __tablename__ = "user_stats"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)  # 主键ID，自增
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)  # 所属用户ID，关联users表，唯一
    favorite_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 收藏总数
    download_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 下载总数
    view_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 浏览总数
    ai_conversation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # AI对话会话总数
    ai_message_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # AI对话消息总数
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)  # 创建时间
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)  # 更新时间，修改自动刷新

    # 反向关联用户主表
    user: Mapped[User] = relationship(
        primaryjoin="User.id == foreign(UserStat.user_id)",
        back_populates="stats",
        lazy="selectin",
    )
