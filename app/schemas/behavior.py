from pydantic import BaseModel, ConfigDict, Field


class ImageViewIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    visitor_id: str | None = Field(default=None, max_length=100)
