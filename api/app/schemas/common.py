from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    code: str = "OK"
    message: str = "success"
    data: T | None = None


class PageParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=100, alias="pageSize")


class PageResult(BaseModel, Generic[T]):
    items: list[T]
    total: int


def ok(data: T | None = None, message: str = "success") -> ApiResponse[T]:
    return ApiResponse(data=data, message=message)
