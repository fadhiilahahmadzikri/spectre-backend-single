from __future__ import annotations

import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


HostedAuthMode = Literal["register", "authenticate", "auto"]


class HostedAuthSessionCreateRequest(BaseModel):
    external_user_id: str = Field(..., min_length=1, max_length=255)
    mode: HostedAuthMode = "authenticate"
    return_url: str
    cancel_url: str
    metadata: dict[str, Any] | None = None


class HostedAuthSessionCreateResponse(BaseModel):
    id: str
    status: str
    mode: HostedAuthMode
    external_user_id: str
    client_secret: str
    hosted_url: str
    expires_at: datetime.datetime


class HostedAuthBootstrapResponse(BaseModel):
    id: str
    status: str
    lifecycle_state: str
    mode: HostedAuthMode
    external_user_id: str | None
    expires_at: datetime.datetime | None
    locked: bool
    return_url: str | None
    cancel_url: str | None
    ui: dict[str, Any]


class HostedAuthCaptureRequest(BaseModel):
    client_secret: str
    image: str
    detail_mode: bool = False


class HostedAuthCaptureResponse(BaseModel):
    id: str
    status: str
    lifecycle_state: str
    exchange_code: str | None
    redirect_url: str | None
    reason_code: str | None = None


class HostedAuthExchangeRequest(BaseModel):
    code: str


class HostedAuthSessionResponse(BaseModel):
    id: str
    app_id: str
    mode: HostedAuthMode
    external_user_id: str | None
    status: str
    lifecycle_state: str
    reason_code: str | None
    created_at: datetime.datetime | None
    locked_at: datetime.datetime | None
    completed_at: datetime.datetime | None
    exchanged_at: datetime.datetime | None


class HostedAuthExchangeResponse(HostedAuthSessionResponse):
    result_token: str | None = None
