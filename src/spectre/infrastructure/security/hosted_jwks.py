from __future__ import annotations

import base64
import datetime
from typing import Any
from uuid import UUID

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import jwt

from spectre.config import Settings


def build_jwks(settings: Settings) -> dict[str, list[dict[str, str]]]:
    key = _load_private_key(settings.hosted_jwt_private_key_pem)
    if key is None:
        return {"keys": []}

    public_numbers = key.public_key().public_numbers()
    return {
        "keys": [
            {
                "kty": "RSA",
                "use": "sig",
                "kid": settings.hosted_jwt_key_id,
                "alg": "RS256",
                "n": _base64url_uint(public_numbers.n),
                "e": _base64url_uint(public_numbers.e),
            }
        ]
    }


def sign_hosted_result_token(
    *,
    settings: Settings,
    session_id: UUID,
    app_id: UUID,
    external_user_id: str | None,
    status: str,
) -> str | None:
    if not settings.hosted_jwt_private_key_pem:
        return None
    now = datetime.datetime.now(datetime.timezone.utc)
    payload: dict[str, Any] = {
        "iss": "spectre",
        "aud": str(app_id),
        "sub": external_user_id or str(session_id),
        "sid": str(session_id),
        "app_id": str(app_id),
        "status": status,
        "iat": now,
        "exp": now + datetime.timedelta(minutes=5),
        "type": "hosted_auth_result",
    }
    return jwt.encode(
        payload,
        settings.hosted_jwt_private_key_pem,
        algorithm="RS256",
        headers={"kid": settings.hosted_jwt_key_id},
    )


def _load_private_key(pem: str | None) -> rsa.RSAPrivateKey | None:
    if not pem:
        return None
    key = serialization.load_pem_private_key(pem.encode("utf-8"), password=None)
    if not isinstance(key, rsa.RSAPrivateKey):
        return None
    return key


def _base64url_uint(value: int) -> str:
    length = (value.bit_length() + 7) // 8
    raw = value.to_bytes(length, "big")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
