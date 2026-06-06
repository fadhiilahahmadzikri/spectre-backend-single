"""ApiKey entity — hashed API credentials for tenant applications."""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID


@dataclass
class ApiKey:
    """Represents a hashed API key bound to a tenant application.

    The full key is returned exactly once at creation. Only the prefix
    (first 12 characters) and bcrypt hash are stored.
    """

    id: UUID
    app_id: UUID
    key_prefix: str  # First 12 chars — for display/lookup
    key_hash: str  # bcrypt hash of the full key
    label: str | None = None
    key_type: Literal["legacy", "publishable", "secret"] = "legacy"
    status: Literal["active", "grace_period", "revoked"] = "active"
    last_used_at: datetime.datetime | None = None
    expires_at: datetime.datetime | None = None
    created_at: datetime.datetime = field(default_factory=datetime.datetime.utcnow)
    revoked_at: datetime.datetime | None = None

    @property
    def is_usable(self) -> bool:
        """Key can be used if active or in grace period."""
        return self.status in ("active", "grace_period")
