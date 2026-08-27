"""桃灵助手请求 Schema。

所有字段保持 Vue ``AssistantChatParams`` / ``CreateConversationParams`` 的命名；
业务层负责空白文本和会话归属校验，以返回与 Node 一致的中文 400/404。
"""

from pydantic import BaseModel, Field


class AiChatIn(BaseModel):
    """发送消息请求；不传 conversation_id 时自动创建会话。"""

    conversation_id: int | None = None
    message: str | None = Field(default=None, max_length=10_000)
    stream: bool | None = None


class AiConversationCreateIn(BaseModel):
    """显式创建空会话请求。"""

    title: str | None = Field(default=None, max_length=200)
