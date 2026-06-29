from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

CommentUsageStatus = Literal["unused", "used"]


class CommentBankItemRead(BaseModel):
    id: int
    doctor_id: int = Field(serialization_alias="doctorId")
    doctor_name: str = Field(serialization_alias="doctorName")
    keyword_id: int | None = Field(default=None, serialization_alias="keywordId")
    keyword: str = ""
    content: str
    status: CommentUsageStatus
    used_device_name: str | None = Field(default=None, serialization_alias="usedDeviceName")
    used_account: str | None = Field(default=None, serialization_alias="usedAccount")
    used_at: datetime | None = Field(default=None, serialization_alias="usedAt")
    created_at: datetime = Field(serialization_alias="createdAt")


class CommentBankImportResponse(BaseModel):
    imported: int
    skipped: int


class CommentBankBatchDeletePayload(BaseModel):
    ids: list[int] = Field(min_length=1)


class CommentBankBatchDeleteResponse(BaseModel):
    deleted: int
