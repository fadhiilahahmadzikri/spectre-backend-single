"""JWT token handler — encode and decode access/refresh tokens.

Uses HS256 (symmetric HMAC) for simplicity in a single-service architecture.
"""

from __future__ import annotations

import datetime
from typing import Any
from uuid import UUID

from jose import JWTError, jwt

from spectre.config import Settings
from spectre.domain.exceptions.auth_exceptions import InvalidTokenError


class JWTHandler:
    """Handles JWT creation and verification."""

    def __init__(self, settings: Settings) -> None:
        self._secret = settings.jwt_secret_key
        self._algorithm = settings.jwt_algorithm
        self._access_expire_minutes = settings.jwt_access_token_expire_minutes

    def create_access_token(
        self,
        user_id: UUID,
        *,
        extra_claims: dict[str, Any] | None = None,
    ) -> str:
        """Create a JWT access token."""
        now = datetime.datetime.now(datetime.timezone.utc)
        expire = now + datetime.timedelta(minutes=self._access_expire_minutes)

        payload = {
            "sub": str(user_id),
            "iat": now,
            "exp": expire,
            "type": "access",
        }
        if extra_claims:
            payload.update(extra_claims)

        return jwt.encode(payload, self._secret, algorithm=self._algorithm)

    def decode_token(self, token: str) -> dict[str, Any]:
        """Decode and validate a JWT token.

        Raises:
            InvalidTokenError: If the token is expired, malformed, or invalid.
        """
        try:
            payload = jwt.decode(token, self._secret, algorithms=[self._algorithm])
            return payload
        except JWTError as exc:
            raise InvalidTokenError(f"Token validation failed: {exc}") from exc

    def get_user_id(self, token: str) -> UUID:
        """Extract user_id from a valid token."""
        payload = self.decode_token(token)
        sub = payload.get("sub")
        if sub is None:
            raise InvalidTokenError("Token missing 'sub' claim.")
        return UUID(sub)
