from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RegionRelationItem(BaseModel):
    id: int
    region: str
    neighbors: list[str]
    created_at: datetime = Field(serialization_alias="createdAt")
    updated_at: datetime = Field(serialization_alias="updatedAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class RegionRelationPayload(BaseModel):
    neighbors: list[str] = Field(default_factory=list)
