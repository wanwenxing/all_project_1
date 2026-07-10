from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    code: int = 0
    data: T | None = None
    message: str = "ok"


def success(data: T | None = None, message: str = "ok") -> ApiResponse[T]:
    return ApiResponse(code=0, data=data, message=message)


def error(code: int, message: str) -> ApiResponse[None]:
    return ApiResponse(code=code, data=None, message=message)
