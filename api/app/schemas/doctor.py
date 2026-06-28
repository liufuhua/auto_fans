from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

RecordStatus = Literal["active", "disabled", "deleted"]


class DoctorKeywordCommentCount(BaseModel):
    keyword_id: int = Field(serialization_alias="keywordId")
    keyword: str
    remaining_comment_count: int = Field(serialization_alias="remainingCommentCount")

    model_config = ConfigDict(populate_by_name=True)


class DoctorItem(BaseModel):
    id: int
    name: str
    real_name: str = Field(default="", serialization_alias="realName")
    sort_order: int = Field(default=0, serialization_alias="sortOrder")
    remark: str
    status: RecordStatus
    remaining_comment_count: int = Field(default=0, serialization_alias="remainingCommentCount")
    keyword_comment_counts: list["DoctorKeywordCommentCount"] = Field(
        default_factory=list, serialization_alias="keywordCommentCounts"
    )
    created_at: datetime = Field(serialization_alias="createdAt")
    updated_at: datetime = Field(serialization_alias="updatedAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class DoctorPayload(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    real_name: str = Field(default="", max_length=64, validation_alias="realName")
    remark: str = Field(default="", max_length=500)


class DoctorSortOrderUpdate(BaseModel):
    id: int
    sort_order: int = Field(ge=1, validation_alias="sortOrder", serialization_alias="sortOrder")

    model_config = ConfigDict(populate_by_name=True)


class DoctorSortOrderPayload(BaseModel):
    items: list[DoctorSortOrderUpdate]

    model_config = ConfigDict(populate_by_name=True)


class DoctorKeywordItem(BaseModel):
    id: int
    doctor_id: int = Field(serialization_alias="doctorId")
    keyword: str
    remark: str
    status: RecordStatus
    remaining_comment_count: int = Field(default=0, serialization_alias="remainingCommentCount")
    created_at: datetime = Field(serialization_alias="createdAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class DoctorKeywordPayload(BaseModel):
    keyword: str = Field(min_length=1, max_length=100)
    remark: str = Field(default="", max_length=500)
