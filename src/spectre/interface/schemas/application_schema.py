"""Application and API key schemas."""

from __future__ import annotations

import datetime
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator


class WebhookUrlMixin(BaseModel):
    webhook_url: str | None = None

    @field_validator("webhook_url")
    @classmethod
    def normalize_webhook_url(cls, value: str | None) -> str | None:
        if value is None:
            return None

        normalized = value.strip()
        if not normalized:
            return None

        parsed = urlparse(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("webhook_url must be an absolute http or https URL.")

        return normalized


class CreateApplicationRequest(WebhookUrlMixin):
    name: str = Field(..., min_length=1, max_length=255)


class UpdateApplicationRequest(WebhookUrlMixin):
    name: str | None = Field(None, max_length=255)
    liveness_threshold: float | None = Field(None, ge=0.0, le=1.0)
    similarity_threshold: float | None = Field(None, ge=0.0, le=1.0)
    allowed_ips: list[str] | None = None


class ApplicationResponse(BaseModel):
    id: str
    name: str
    webhook_url: str | None
    has_webhook: bool
    webhook_secret: str | None = None
    liveness_threshold: float
    similarity_threshold: float
    allowed_ips: list[str]
    status: str
    created_at: datetime.datetime
    updated_at: datetime.datetime


class GenerateApiKeyRequest(BaseModel):
    label: str | None = Field(None, max_length=255)


class ApiKeyResponse(BaseModel):
    id: str
    key_prefix: str
    label: str | None
    status: str
    last_used_at: datetime.datetime | None
    created_at: datetime.datetime


class ApiKeyCreatedResponse(ApiKeyResponse):
    full_key: str  # Returned exactly once
