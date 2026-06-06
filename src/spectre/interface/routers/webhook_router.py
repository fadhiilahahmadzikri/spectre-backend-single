from __future__ import annotations

import secrets
import uuid
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request, status

from spectre.config import Settings
from spectre.infrastructure.repositories.sql_repositories import (
    SQLAuditLogRepository,
    SQLTenantApplicationRepository,
    SQLWebhookRepository,
)
from spectre.infrastructure.security.aes_encryption import AESEncryption
from spectre.interface.dependencies import CurrentUser, DBSession, get_settings
from spectre.interface.schemas.webhook_schema import (
    CreateWebhookEndpointRequest,
    WebhookEndpointCreatedResponse,
    WebhookEndpointResponse,
)

router = APIRouter(prefix="/api/v1/applications", tags=["Webhooks"])


@router.post(
    "/{app_id}/webhook-endpoints",
    status_code=201,
    response_model=WebhookEndpointCreatedResponse,
)
async def create_webhook_endpoint(
    app_id: uuid.UUID,
    body: CreateWebhookEndpointRequest,
    request: Request,
    db: DBSession,
    current_user: CurrentUser,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    await _assert_app_owner(db, app_id, current_user.id)
    _validate_endpoint_url(body.url)

    secret = f"whsec_{secrets.token_urlsafe(32)}"
    encrypted = AESEncryption(settings).encrypt_string(secret)
    endpoint = await SQLWebhookRepository(db).create_endpoint(
        endpoint_id=uuid.uuid4(),
        app_id=app_id,
        url=body.url,
        secret_encrypted=encrypted,
        event_types=body.event_types,
    )
    await _append_webhook_audit(
        db,
        request,
        app_id=app_id,
        event_type="webhook_endpoint.created",
        resource_id=endpoint["id"],
    )
    endpoint.pop("secret_encrypted", None)
    endpoint["secret"] = secret
    return endpoint


@router.get(
    "/{app_id}/webhook-endpoints",
    response_model=dict,
)
async def list_webhook_endpoints(
    app_id: uuid.UUID,
    db: DBSession,
    current_user: CurrentUser,
) -> dict[str, list[WebhookEndpointResponse]]:
    await _assert_app_owner(db, app_id, current_user.id)
    endpoints = await SQLWebhookRepository(db).list_endpoints_by_app(app_id)
    return {"data": endpoints}


@router.delete("/{app_id}/webhook-endpoints/{endpoint_id}", status_code=204)
async def disable_webhook_endpoint(
    app_id: uuid.UUID,
    endpoint_id: uuid.UUID,
    request: Request,
    db: DBSession,
    current_user: CurrentUser,
) -> None:
    await _assert_app_owner(db, app_id, current_user.id)
    disabled = await SQLWebhookRepository(db).disable_endpoint(endpoint_id, app_id)
    if not disabled:
        raise HTTPException(status_code=404, detail="Webhook endpoint not found.")
    await _append_webhook_audit(
        db,
        request,
        app_id=app_id,
        event_type="webhook_endpoint.disabled",
        resource_id=str(endpoint_id),
    )
    return None


async def _assert_app_owner(db: Any, app_id: uuid.UUID, user_id: uuid.UUID) -> None:
    app = await SQLTenantApplicationRepository(db).get_by_id(app_id)
    if not app or app.owner_id != user_id:
        raise HTTPException(status_code=404, detail="Application not found.")


def _validate_endpoint_url(url: str) -> None:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error_code": "INVALID_WEBHOOK_URL", "message": "URL must be absolute."},
        )
    if parsed.scheme == "https":
        return
    if parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1"}:
        return
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={
            "error_code": "INSECURE_WEBHOOK_URL",
            "message": "Webhook endpoints must use https outside localhost.",
        },
    )


async def _append_webhook_audit(
    db: Any,
    request: Request,
    *,
    app_id: uuid.UUID,
    event_type: str,
    resource_id: str,
) -> None:
    await SQLAuditLogRepository(db).append(
        event_type=event_type,
        app_id=app_id,
        resource_type="webhook_endpoint",
        resource_id=resource_id,
        ip_address=request.client.host if request.client else None,
    )
