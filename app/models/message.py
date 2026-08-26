"""
留言模块数据模型。

定义用户留言表 UserMessage，支持楼中楼回复（parent_id），
并记录阿里云内容安全审核的状态与结果。
"""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, String, Text
from sqlalchemy.dialects.mysql import ENUM, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class UserMessage(Base):
    """用户留言表：网站留言/评论数据，支持楼中楼回复与内容安全审核。"""

    __tablename__ = "user_messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # 主键ID
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)  # 留言用户ID，关联users表
    parent_id: Mapped[int | None] = mapped_column(BigInteger)  # 父留言ID，为空表示楼顶层，否则为回复
    content: Mapped[str] = mapped_column(Text, nullable=False)  # 留言正文
    check_status: Mapped[str] = mapped_column(
        ENUM("pending", "success", "block"),  # 内容审核状态：pending待审核 / success通过 / block拦截
        nullable=False,
        default="pending",
    )
    check_score: Mapped[float | None] = mapped_column(Float)  # 审核风险分数（越高风险越大）
    check_result: Mapped[dict | None] = mapped_column(JSON)  # 审核结果明细（阿里云原始返回）
    ip_address: Mapped[str | None] = mapped_column(String(64))  # 留言者IP地址
    user_agent: Mapped[str | None] = mapped_column(String(500))  # 留言者浏览器 UA 标识
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)  # 留言时间
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now, onupdate=datetime.now  # 更新时间，审核后刷新
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime)  # 软删除时间，为空表示未删除
