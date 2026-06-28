from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AutomationTimingSettingItem(BaseModel):
    id: int
    key: str
    label: str
    min_seconds: float = Field(serialization_alias="minSeconds")
    max_seconds: float = Field(serialization_alias="maxSeconds")
    created_at: datetime = Field(serialization_alias="createdAt")
    updated_at: datetime = Field(serialization_alias="updatedAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class AutomationTimingSettingPayload(BaseModel):
    min_seconds: float = Field(ge=0, validation_alias="minSeconds")
    max_seconds: float = Field(ge=0, validation_alias="maxSeconds")


class AutomationTimingSettingPayloadWithKey(AutomationTimingSettingPayload):
    key: str = Field(min_length=1, max_length=64)


class AutomationTimingSettingsPayload(BaseModel):
    items: list[AutomationTimingSettingPayloadWithKey]
