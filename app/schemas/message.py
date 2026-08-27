from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class MessageCreateIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    content: str = Field(max_length=2000)
    parent_id: int | None = Field(
        default=None,
        validation_alias=AliasChoices("parent_id", "parentId"),
        gt=0,
    )
