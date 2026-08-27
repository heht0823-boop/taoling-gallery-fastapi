"""收藏、下载和浏览行为的请求 Schema。

``AliasChoices`` 同时接受 Node/Vue 历史字段和当前 snake_case 字段，序列化输出
仍由业务服务固定，防止迁移期间前端调用失效。
"""

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class ImageViewIn(BaseModel):
    """记录图片浏览时携带的可选游客标识。"""

    model_config = ConfigDict(extra="ignore")

    visitor_id: str | None = Field(default=None, max_length=100)


class ImageIdIn(BaseModel):
    """收藏和下载兼容接口使用的图片标识请求。"""

    model_config = ConfigDict(extra="ignore")

    image_id: int = Field(validation_alias=AliasChoices("image_id", "imageId"), gt=0)
