"""收藏、下载和浏览行为的请求 Schema。

``AliasChoices`` 同时接受 Node/Vue 历史字段和当前 snake_case 字段，序列化输出
仍由业务服务固定，防止迁移期间前端调用失效。
"""

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class ImageViewIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    visitor_id: str | None = Field(default=None, max_length=100)


class ImageIdIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    image_id: int = Field(validation_alias=AliasChoices("image_id", "imageId"), gt=0)
