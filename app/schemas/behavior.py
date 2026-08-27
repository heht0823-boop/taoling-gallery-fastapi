from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class ImageViewIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    visitor_id: str | None = Field(default=None, max_length=100)


class ImageIdIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    image_id: int = Field(validation_alias=AliasChoices("image_id", "imageId"), gt=0)
