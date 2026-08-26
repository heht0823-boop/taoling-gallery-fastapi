"""
管理员操作日志模块数据模型。

定义管理员操作审计日志表 AdminLog，
记录谁在什么时间对哪个目标做了什么操作，便于审计与追责。
"""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AdminLog(Base):
    """管理员操作日志表：管理后台所有关键操作的审计记录。"""

    __tablename__ = "admin_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # 主键ID
    actor_id: Mapped[int | None] = mapped_column(BigInteger)  # 操作者用户ID，关联users表
    actor_name: Mapped[str | None] = mapped_column(String(100))  # 操作者用户名（快照，账号改名仍可追溯）
    actor_role: Mapped[str | None] = mapped_column(String(32))  # 操作者角色（如 admin）
    action_type: Mapped[str] = mapped_column(String(100), nullable=False)  # 操作类型（如 create/update/delete）
    target_type: Mapped[str | None] = mapped_column(String(100))  # 被操作对象类型（如图片、用户）
    target_id: Mapped[int | None] = mapped_column(BigInteger)  # 被操作对象ID
    title: Mapped[str] = mapped_column(String(200), nullable=False)  # 日志标题（一句话描述操作）
    content: Mapped[str | None] = mapped_column(Text)  # 日志详情（操作前后数据等）
    ip_address: Mapped[str | None] = mapped_column(String(64))  # 操作者IP地址
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)  # 操作时间
