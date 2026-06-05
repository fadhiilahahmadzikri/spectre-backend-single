"""Password hashing — bcrypt with configurable cost factor."""

from __future__ import annotations

from passlib.context import CryptContext

from spectre.config import Settings


class PasswordHandler:
    """Handles password hashing and verification using bcrypt."""

    def __init__(self, settings: Settings) -> None:
        self._context = CryptContext(
            schemes=["bcrypt"],
            deprecated="auto",
            bcrypt__rounds=settings.bcrypt_cost,
        )

    def hash(self, password: str) -> str:
        """Hash a plaintext password."""
        return self._context.hash(password)

    def verify(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a plaintext password against a hash."""
        return self._context.verify(plain_password, hashed_password)
