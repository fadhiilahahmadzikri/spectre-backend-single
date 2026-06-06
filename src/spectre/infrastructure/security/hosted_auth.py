from __future__ import annotations

import base64
import datetime
import hashlib
import hmac
import json
import secrets
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from uuid import UUID

from fastapi import HTTPException, status

from spectre.config import Settings
from spectre.domain.entities.tenant_application import TenantApplication


def utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def hash_token(token: str, settings: Settings) -> str:
    pepper = (settings.secret_key or settings.jwt_secret_key).encode("utf-8")
    digest = hmac.new(pepper, token.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"sha256:{digest}"


def verify_token_hash(token: str, token_hash: str | None, settings: Settings) -> bool:
    if not token_hash:
        return False
    return hmac.compare_digest(hash_token(token, settings), token_hash)


def create_client_secret(
    *, app_id: UUID, idempotency_key: str | None, settings: Settings
) -> str:
    if idempotency_key:
        material = f"{app_id}:{idempotency_key}:client_secret".encode("utf-8")
        pepper = (settings.secret_key or settings.jwt_secret_key).encode("utf-8")
        digest = hmac.new(pepper, material, hashlib.sha256).digest()
        token = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
        return f"hcs_{token}"
    return f"hcs_{secrets.token_urlsafe(32)}"


def create_exchange_code() -> str:
    return f"hex_{secrets.token_urlsafe(32)}"


def request_fingerprint(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def origin_from_url(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error_code": "INVALID_REDIRECT_URL", "message": "URL must be absolute."},
        )
    port = f":{parsed.port}" if parsed.port else ""
    hostname = parsed.hostname or parsed.netloc
    return f"{parsed.scheme.lower()}://{hostname.lower()}{port}"


def validate_redirect_url(url: str, app: TenantApplication) -> str:
    parsed = urlparse(url)
    origin = origin_from_url(url)
    allowed = {allowed.rstrip("/") for allowed in (app.allowed_origins or [])}
    if origin not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": "REDIRECT_ORIGIN_NOT_ALLOWED",
                "message": f"Origin '{origin}' is not allowed for this application.",
            },
        )
    if parsed.scheme != "https" and origin not in {
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    }:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": "INSECURE_REDIRECT_URL",
                "message": "Hosted auth redirects must use https outside localhost.",
            },
        )
    return url


def append_query_params(url: str, params: dict[str, str]) -> str:
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.update(params)
    return urlunparse(parsed._replace(query=urlencode(query)))


def build_hosted_auth_url(
    *, base_url: str, session_id: UUID, client_secret: str
) -> str:
    base = base_url.rstrip("/")
    return f"{base}/hosted/auth/{session_id}?{urlencode({'client_secret': client_secret})}"
