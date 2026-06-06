from __future__ import annotations

import datetime

from pydantic import BaseModel, Field


class CreateWebhookEndpointRequest(BaseModel):
    url: str
    event_types: list[str] = Field(default_factory=list)


class WebhookEndpointCreatedResponse(BaseModel):
    id: str
    app_id: str
    url: str
    event_types: list[str]
    status: str
    secret: str
    created_at: datetime.datetime | None


class WebhookEndpointResponse(BaseModel):
    id: str
    app_id: str
    url: str
    event_types: list[str]
    status: str
    created_at: datetime.datetime | None
    disabled_at: datetime.datetime | None
