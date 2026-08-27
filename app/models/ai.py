"""
AI 对话模块数据模型。

定义 AI 陪聊/图片推荐功能相关的三张表：
会话（AiConversation）、消息（AiMessage）、记忆（AiMemory）。
"""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, Text
from sqlalchemy.dialects.mysql import ENUM, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AiConversation(Base):
    """AI对话会话表：一次 AI 聊天的会话主题，是消息的归属容器。"""

    __tablename__ = "ai_conversations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # 主键ID
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)  # 所属用户ID，关联users表
    title: Mapped[str] = mapped_column(String(200), nullable=False)  # 会话标题（如首次提问的摘要）
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)  # 创建时间
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now, onupdate=datetime.now  # 最近对话时间，修改自动刷新
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime)  # 软删除时间，为空表示未删除


class AiMessage(Base):
    """AI对话消息表：会话内的一条条消息，包含用户提问与 AI 回复。"""

    __tablename__ = "ai_messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # 主键ID
    # 所属会话ID，关联ai_conversations表
    conversation_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)  # 所属用户ID，关联users表
    # 消息角色：user提问 / assistant回答
    role: Mapped[str] = mapped_column(ENUM("user", "assistant"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)  # 消息正文内容
    recommended_tags: Mapped[list | None] = mapped_column(JSON)  # AI回复中推荐的图片标签列表
    recommended_image_ids: Mapped[list | None] = mapped_column(JSON)  # AI回复中推荐的图片ID列表
    # 消息发送时间
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime)  # 软删除时间，为空表示未删除


class AiMemory(Base):
    """AI记忆表：沉淀用户偏好等记忆信息，供 AI 后续对话个性化参考。"""

    __tablename__ = "ai_memories"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # 主键ID
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)  # 所属用户ID，关联users表
    conversation_id: Mapped[int | None] = mapped_column(BigInteger)  # 来源会话ID，为空表示跨会话的全局记忆
    # 记忆类型：short短期 / long长期
    memory_type: Mapped[str] = mapped_column(ENUM("short", "long"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)  # 记忆内容
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)  # 创建时间
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now, onupdate=datetime.now  # 更新时间，修改自动刷新
    )
