"""RefreshToken entity — opaque long-lived token for JWT access token rotation."""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from uuid import UUID


@dataclass
class RefreshToken:
    """Represents a refresh token for JWT rotation.

    The raw token value is SHA-256 hashed before storage.
    Rotation invalidates the previous token immediately.
    """

    id: UUID
    user_id: UUID
    token_hash: str  # SHA-256 hash of the opaque token
    is_revoked: bool = False
    expires_at: datetime.datetime = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
        + datetime.timedelta(days=7)
    )
    created_at: datetime.datetime = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )

    @property
    def is_expired(self) -> bool:
        return datetime.datetime.now(datetime.timezone.utc) > self.expires_at

    @property
    def is_valid(self) -> bool:
        return not self.is_revoked and not self.is_expired
