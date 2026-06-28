from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

AdminUserStatus = Literal["active", "disabled"]


class AdminUserItem(BaseModel):
    id: int
    phone: str
    username: str
    status: AdminUserStatus
    created_at: datetime = Field(serialization_alias="createdAt")
    last_login_at: datetime | None = Field(default=None, serialization_alias="lastLoginAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class AdminUserCreate(BaseModel):
    phone: str = Field(min_length=1, max_length=20)
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=6, max_length=128)


class AdminUserUpdate(BaseModel):
    phone: str = Field(min_length=1, max_length=20)
    username: str = Field(min_length=1, max_length=64)


class AdminUserResetPassword(BaseModel):
    password: str = Field(min_length=6, max_length=128)
