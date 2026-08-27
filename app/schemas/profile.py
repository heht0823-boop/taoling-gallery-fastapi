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
