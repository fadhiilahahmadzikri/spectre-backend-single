"""Client logging telemetry schema."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ClientLogRequest(BaseModel):
    """Schema for receiving frontend/client telemetry logs."""
    
    level: str = Field(default="error", description="Log level: info, warning, error")
    message: str = Field(..., description="The main log message or error description")
    context: dict[str, Any] | None = Field(default=None, description="Detailed context, stack trace, or server response payload")
    source: str = Field(default="unknown_client", description="Identifier of the client app (e.g., 'POC_Client')")
