from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DoctorProvinceItem(BaseModel):
    doctor_id: int = Field(serialization_alias="doctorId")
    doctor_name: str = Field(serialization_alias="doctorName")
    provinces: list[str]
    updated_at: datetime | None = Field(default=None, serialization_alias="updatedAt")


class DoctorProvincePayload(BaseModel):
    provinces: list[str] = Field(default_factory=list)

    @field_validator("provinces")
    @classmethod
    def normalize_provinces(cls, value: list[str]) -> list[str]:
        provinces: list[str] = []
        for item in value:
            province = item.strip()
            if not province or province in provinces:
                continue
            if len(province) > 32:
                raise ValueError("省份长度不能超过 32 个字符")
            provinces.append(province)
        return provinces

    model_config = ConfigDict(str_strip_whitespace=True)
