from __future__ import annotations

import hashlib
import hmac
import time


def sign_webhook_payload(raw_body: bytes, secret: str, timestamp: int | None = None) -> str:
    ts = int(time.time()) if timestamp is None else timestamp
    signed_payload = f"{ts}.".encode("utf-8") + raw_body
    digest = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    return f"t={ts},v1={digest}"


def verify_webhook_signature(
    raw_body: bytes,
    signature_header: str,
    secret: str,
    *,
    tolerance_seconds: int = 300,
    now: int | None = None,
) -> bool:
    parts = _parse_signature_header(signature_header)
    timestamp = int(parts.get("t", "0"))
    received = parts.get("v1", "")
    current = int(time.time()) if now is None else now
    if abs(current - timestamp) > tolerance_seconds:
        return False
    expected = sign_webhook_payload(raw_body, secret, timestamp).split("v1=", 1)[1]
    return hmac.compare_digest(expected, received)


def _parse_signature_header(header: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for item in header.split(","):
        key, _, value = item.partition("=")
        if key and value:
            values[key.strip()] = value.strip()
    return values
