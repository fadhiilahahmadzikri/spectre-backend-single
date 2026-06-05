"""HMAC-SHA256 webhook payload signer.

Signs webhook payloads so the receiving tenant can verify authenticity.
Signature format: sha256={hex_digest}
"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any


class HMACSigner:
    """Signs webhook payloads with HMAC-SHA256."""

    @staticmethod
    def sign(payload: dict[str, Any], secret: str) -> str:
        """Sign a JSON payload with the webhook secret.

        Args:
            payload: The webhook payload dict to sign.
            secret: The tenant's webhook secret (plaintext).

        Returns:
            Signature string in format: sha256={hex_digest}
        """
        payload_bytes = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        digest = hmac.new(
            secret.encode("utf-8"), payload_bytes, hashlib.sha256
        ).hexdigest()
        return f"sha256={digest}"

    @staticmethod
    def verify(payload: dict[str, Any], secret: str, signature: str) -> bool:
        """Verify a webhook signature.

        Args:
            payload: The received payload dict.
            secret: The webhook secret.
            signature: The received signature string.

        Returns:
            True if the signature is valid.
        """
        expected = HMACSigner.sign(payload, secret)
        return hmac.compare_digest(expected, signature)

    @staticmethod
    def payload_hash(payload: dict[str, Any]) -> str:
        """Compute SHA-256 hash of a payload for deduplication."""
        payload_bytes = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(payload_bytes).hexdigest()
