"""User entity — tenant account holder."""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from uuid import UUID


@dataclass
class User:
    """Represents a tenant account holder who manages applications."""

    id: UUID
    email: str
    display_name: str | None = None
    totp_secret_encrypted: str | None = None
    totp_enabled: bool = False
    role: str = "user"
    is_active: bool = True
    created_at: datetime.datetime = field(default_factory=datetime.datetime.utcnow)
    updated_at: datetime.datetime = field(default_factory=datetime.datetime.utcnow)

    @property
    def requires_totp(self) -> bool:
        """Check if user has TOTP enabled and must verify during login."""
        return self.totp_enabled and self.totp_secret_encrypted is not None

@dataclass
class UserIdentity:
    """Represents an authentication method linked to a user."""

    id: UUID
    user_id: UUID
    provider: str  # e.g., 'local', 'google'
    provider_user_id: str
    password_hash: str | None = None
    access_token: str | None = None
    refresh_token: str | None = None
    created_at: datetime.datetime = field(default_factory=datetime.datetime.utcnow)
    last_used_at: datetime.datetime = field(default_factory=datetime.datetime.utcnow)
