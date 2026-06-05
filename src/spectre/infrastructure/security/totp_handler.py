"""TOTP handler — setup, verification, and QR URI generation (RFC 6238)."""

from __future__ import annotations

import pyotp

from spectre.config import Settings


class TOTPHandler:
    """Handles TOTP (Time-Based One-Time Password) operations."""

    def __init__(self, settings: Settings) -> None:
        self._issuer = settings.totp_issuer_name

    def generate_secret(self) -> str:
        """Generate a new TOTP secret (base32 encoded)."""
        return pyotp.random_base32()

    def get_provisioning_uri(self, secret: str, email: str) -> str:
        """Generate the otpauth:// URI for QR code scanning."""
        totp = pyotp.TOTP(secret)
        return totp.provisioning_uri(name=email, issuer_name=self._issuer)

    def verify(self, secret: str, code: str) -> bool:
        """Verify a TOTP code against the secret.

        Allows a ±1 time step window (±30 seconds) for clock drift.
        """
        totp = pyotp.TOTP(secret)
        return totp.verify(code, valid_window=1)
