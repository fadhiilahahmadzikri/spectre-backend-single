"""TenantApplication entity — per-app configuration and isolation boundary."""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID


@dataclass
class TenantApplication:
    """Represents a single application registered by a tenant.

    Each application has its own API keys, face profiles, webhook config,
    and liveness thresholds. This is the primary tenant isolation boundary.
    """

    id: UUID
    owner_id: UUID
    name: str
    webhook_url: str | None = None
    webhook_secret_encrypted: str | None = None
    liveness_threshold: float = 0.5
    similarity_threshold: float = 0.75
    allowed_ips: list[str] = field(default_factory=list)
    status: Literal["active", "suspended", "deleted"] = "active"
    created_at: datetime.datetime = field(default_factory=datetime.datetime.utcnow)
    updated_at: datetime.datetime = field(default_factory=datetime.datetime.utcnow)

    @property
    def is_active(self) -> bool:
        return self.status == "active"

    @property
    def has_webhook(self) -> bool:
        return self.webhook_url is not None and self.webhook_secret_encrypted is not None
