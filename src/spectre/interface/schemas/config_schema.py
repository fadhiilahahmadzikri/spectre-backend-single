"""Pydantic schemas for the Configuration API."""

from __future__ import annotations

from pydantic import BaseModel


class ConfigItem(BaseModel):
    key: str
    value: str
    category: str
    data_type: str
    description: str
    updated_by: str | None = None
    updated_at: str | None = None


class ConfigResponse(BaseModel):
    """GET /admin/config response — grouped by category."""
    categories: dict[str, list[ConfigItem]]


class ConfigUpdateRequest(BaseModel):
    """PATCH /admin/config request — key-value pairs to update."""
    updates: dict[str, str]
