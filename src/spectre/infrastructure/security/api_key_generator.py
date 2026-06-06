"""API key generator — create, hash, and verify API keys.

Formats: spk_{random_hex} legacy keys, spub_{random_hex} publishable keys,
and ssk_{random_hex} secret keys. The full key is shown once. Only prefix
(first 12 chars) and bcrypt hash are stored.
"""

from __future__ import annotations

import secrets

from passlib.context import CryptContext

from spectre.config import Settings
from spectre.domain.value_objects.api_key_pair import ApiKeyPair


class ApiKeyGenerator:
    """Generates and verifies API keys."""

    _LEGACY_PREFIX = "spk_"
    _PUBLISHABLE_PREFIX = "spub_"
    _SECRET_PREFIX = "ssk_"

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
        return self._generate_with_prefix(self._LEGACY_PREFIX)

    def generate_for_type(self, key_type: str) -> ApiKeyPair:
        """Generate a key pair using the prefix for a key semantic type."""
        if key_type == "publishable":
            return self._generate_with_prefix(self._PUBLISHABLE_PREFIX)
        if key_type == "secret":
            return self._generate_with_prefix(self._SECRET_PREFIX)
        return self.generate()

    @staticmethod
    def is_secret_key(plain_key: str) -> bool:
        return plain_key.startswith(ApiKeyGenerator._SECRET_PREFIX)

    @staticmethod
    def is_publishable_key(plain_key: str) -> bool:
        return plain_key.startswith(ApiKeyGenerator._PUBLISHABLE_PREFIX)

    def _generate_with_prefix(self, prefix: str) -> ApiKeyPair:
        random_part = secrets.token_hex(self._key_length // 2)
        full_key = f"{prefix}{random_part}"
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
