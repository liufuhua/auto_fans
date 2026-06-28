from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AdminUserRead(BaseModel):
    id: int
    phone: str
    username: str
    is_active: bool = Field(serialization_alias="isActive")
    last_login_at: datetime | None = Field(default=None, serialization_alias="lastLoginAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class LoginRequest(BaseModel):
    account: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class LoginResponse(BaseModel):
    token: str
    user: AdminUserRead


class TokenPayload(BaseModel):
    sub: str
    type: str = "access"
