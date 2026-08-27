"""管理后台请求 Schema 与 Node 字段兼容规则。

管理图片请求优先接受标准 snake_case，同时兼容旧控制器中的 ``categoryId`` 和
``tagIds``；状态使用 Literal 在进入服务层前拒绝未知值。
"""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

ImageStatus = Literal["public", "private", "draft", "deleted"]
RecordStatus = Literal["normal", "disabled"]


class ImageCreateIn(BaseModel):
    """创建图片元数据；文件上传由独立 multipart 接口完成。"""

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
        """把 Node/前端可能提交的驼峰关联字段归一为内部名称。"""

        if not isinstance(value, dict):
            return value
        data = dict(value)
        if "category_id" not in data and "categoryId" in data:
            data["category_id"] = data["categoryId"]
        if "tag_ids" not in data and "tagIds" in data:
            data["tag_ids"] = data["tagIds"]
        return data


class ImageUpdateIn(BaseModel):
    """局部更新图片；所有字段可省略，未提交字段保持原值。"""

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
        """复用创建接口的字段别名语义，避免 PUT/PATCH 表现不一致。"""

        if not isinstance(value, dict):
            return value
        data = dict(value)
        if "category_id" not in data and "categoryId" in data:
            data["category_id"] = data["categoryId"]
        if "tag_ids" not in data and "tagIds" in data:
            data["tag_ids"] = data["tagIds"]
        return data


class ImageStatusIn(BaseModel):
    """图片可见状态修改请求。"""

    status: ImageStatus


class ImageRestoreIn(BaseModel):
    """软删除图片恢复请求；恢复后不能继续保持 deleted。"""

    status: Literal["public", "private", "draft"] = "draft"


class CategoryCreateIn(BaseModel):
    """创建分类请求。"""

    name: str
    sort_order: int = 0
    status: RecordStatus = "normal"


class CategoryUpdateIn(BaseModel):
    """局部修改分类请求。"""

    name: str | None = None
    sort_order: int | None = None
    status: RecordStatus | None = None


class TagCreateIn(BaseModel):
    """创建标签请求。"""

    name: str
    color: str | None = None
    status: RecordStatus = "normal"


class TagUpdateIn(BaseModel):
    """局部修改标签请求。"""

    name: str | None = None
    color: str | None = None
    status: RecordStatus | None = None


class UserStatusIn(BaseModel):
    """启用或禁用普通用户请求。"""

    status: RecordStatus


class AdminMessageReplyIn(BaseModel):
    """管理员回复一条顶层留言的正文。"""

    content: str
