"""API key generator — create, hash, and verify API keys.

Format: spk_{random_hex}
The full key is shown once. Only prefix (12 chars) and bcrypt hash are stored.
"""

from __future__ import annotations

import secrets

from passlib.context import CryptContext

from spectre.config import Settings
from spectre.domain.value_objects.api_key_pair import ApiKeyPair


class ApiKeyGenerator:
    """Generates and verifies API keys."""

    _PREFIX = "spk_"

    def __init__(self, settings: Settings) -> None:
        self._key_length = settings.api_key_length
        self._context = CryptContext(
            schemes=["bcrypt"],
            deprecated="auto",
            bcrypt__rounds=settings.bcrypt_cost,
        )

    def generate(self) -> ApiKeyPair:
        """Generate a new API key pair.

        Returns:
            ApiKeyPair with full_key (shown once), prefix (stored), and hash (stored).
        """
        random_part = secrets.token_hex(self._key_length // 2)
        full_key = f"{self._PREFIX}{random_part}"
        prefix = full_key[:12]
        key_hash = self._context.hash(full_key)

        return ApiKeyPair(
            full_key=full_key,
            prefix=prefix,
            key_hash=key_hash,
        )

    def verify(self, plain_key: str, key_hash: str) -> bool:
        """Verify a plaintext API key against a stored hash."""
        return self._context.verify(plain_key, key_hash)
