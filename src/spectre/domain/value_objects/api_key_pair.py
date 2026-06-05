"""ApiKeyPair value object — generated key pair for one-time display."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ApiKeyPair:
    """Represents a newly generated API key pair.

    The full_key is returned to the user exactly once at creation.
    Only the prefix and bcrypt hash are stored.

    Format: spk_{random_token}
    Prefix: first 12 chars (e.g., 'spk_a1b2c3d4')
    """

    full_key: str  # Full plaintext key — returned once, never stored
    prefix: str  # First 12 chars — stored for display/lookup
    key_hash: str  # bcrypt hash — stored for verification
