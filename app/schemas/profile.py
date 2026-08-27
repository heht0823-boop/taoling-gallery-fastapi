"""个人资料、远程头像与密码修改请求 Schema。

字段别名覆盖 Vue 与旧 Node 控制器使用的两套命名，服务层接收后统一标准化。
"""

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class ProfileUpdateIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    username: str | None = Field(default=None, max_length=64)
    email: str | None = Field(default=None, max_length=128)
    avatar_url: str | None = Field(default=None, max_length=500)


class PasswordUpdateIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    old_password: str = Field(
        validation_alias=AliasChoices("old_password", "oldPassword"),
        min_length=1,
    )
    new_password: str = Field(
        validation_alias=AliasChoices("new_password", "newPassword"),
        min_length=6,
        max_length=128,
    )
