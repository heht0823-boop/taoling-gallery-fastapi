from typing import Literal

from pydantic import BaseModel, Field, model_validator

ImageStatus = Literal["public", "private", "draft", "deleted"]
RecordStatus = Literal["normal", "disabled"]


class ImageCreateIn(BaseModel):
    title: str
    image_url: str
    description: str | None = None
    thumbnail_url: str | None = None
    category_id: int | None = None
    aspect_ratio: str | None = None
    status: ImageStatus = "draft"
    display_weight: int = 0
    tag_ids: list[int] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def accept_node_aliases(cls, value):
        if not isinstance(value, dict):
            return value
        data = dict(value)
        if "category_id" not in data and "categoryId" in data:
            data["category_id"] = data["categoryId"]
        if "tag_ids" not in data and "tagIds" in data:
            data["tag_ids"] = data["tagIds"]
        return data


class ImageUpdateIn(BaseModel):
    title: str | None = None
    image_url: str | None = None
    description: str | None = None
    thumbnail_url: str | None = None
    category_id: int | None = None
    aspect_ratio: str | None = None
    status: ImageStatus | None = None
    display_weight: int | None = None
    tag_ids: list[int] | None = None

    @model_validator(mode="before")
    @classmethod
    def accept_node_aliases(cls, value):
        if not isinstance(value, dict):
            return value
        data = dict(value)
        if "category_id" not in data and "categoryId" in data:
            data["category_id"] = data["categoryId"]
        if "tag_ids" not in data and "tagIds" in data:
            data["tag_ids"] = data["tagIds"]
        return data


class ImageStatusIn(BaseModel):
    status: ImageStatus


class ImageRestoreIn(BaseModel):
    status: Literal["public", "private", "draft"] = "draft"


class CategoryCreateIn(BaseModel):
    name: str
    sort_order: int = 0
    status: RecordStatus = "normal"


class CategoryUpdateIn(BaseModel):
    name: str | None = None
    sort_order: int | None = None
    status: RecordStatus | None = None


class TagCreateIn(BaseModel):
    name: str
    color: str | None = None
    status: RecordStatus = "normal"


class TagUpdateIn(BaseModel):
    name: str | None = None
    color: str | None = None
    status: RecordStatus | None = None


class UserStatusIn(BaseModel):
    status: RecordStatus


class AdminMessageReplyIn(BaseModel):
    content: str
