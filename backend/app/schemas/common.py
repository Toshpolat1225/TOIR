from typing import Generic, TypeVar

from pydantic import BaseModel, Field

ItemT = TypeVar("ItemT")


class PaginatedResponse(BaseModel, Generic[ItemT]):
    items: list[ItemT]
    total: int
    limit: int = Field(default=50, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)
