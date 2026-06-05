"""Common response schemas — standard envelope, error response, pagination."""

from __future__ import annotations

import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None


class StandardResponse(BaseModel, Generic[T]):
    """Standard API response envelope."""
    success: bool = True
    data: T
    request_id: str | None = None
    timestamp: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc))


class ErrorResponse(BaseModel):
    """Standard API error response."""
    success: bool = False
    error: ErrorDetail
    request_id: str | None = None
    timestamp: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc))


class PaginatedData(BaseModel, Generic[T]):
    items: list[T]
    total: int = 0
    offset: int = 0
    limit: int = 50
