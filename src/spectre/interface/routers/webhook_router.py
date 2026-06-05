"""Webhook management router — test ping, list deliveries, retry.

All endpoints from API_SPECIFICATION.md §4.7.
All require JWT Bearer authentication.
"""

from __future__ import annotations

import datetime
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request

from spectre.config import Settings
from spectre.domain.exceptions.tenant_exceptions import ApplicationNotFoundError
from spectre.interface.dependencies import CurrentUser, DBSession, get_settings
from spectre.infrastructure.repositories.sql_repositories import (
    SQLTenantApplicationRepository,
    SQLWebhookDeliveryRepository,
)

router = APIRouter(prefix="/api/v1/applications", tags=["Webhooks"])


@router.post("/{app_id}/webhooks/test")
async def test_webhook(
    app_id: uuid.UUID,
    db: DBSession,
    current_user: CurrentUser,
    settings: Settings = Depends(get_settings),
) -> dict:
    """Send a test ping to the configured webhook URL."""
    app_repo = SQLTenantApplicationRepository(db)
    app = await app_repo.get_by_id(app_id)
    if not app or app.owner_id != current_user.id:
        raise ApplicationNotFoundError()

    if not app.webhook_url:
        raise HTTPException(status_code=400, detail="No webhook URL configured.")

    from spectre.infrastructure.security.aes_encryption import AESEncryption
    from spectre.infrastructure.webhook.http_dispatcher import WebhookDispatcher

    encryption = AESEncryption(settings)
    secret = encryption.decrypt_string(app.webhook_secret_encrypted)

    test_payload = {
        "event": "webhook.test",
        "app_id": str(app_id),
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }

    dispatcher = WebhookDispatcher(settings)
    start = time.monotonic()
    result = await dispatcher.deliver(app.webhook_url, test_payload, secret)
    elapsed_ms = int((time.monotonic() - start) * 1000)

    return {
        "success": result.success,
        "http_status": result.status_code,
        "response_time_ms": elapsed_ms,
        "target_url": app.webhook_url,
        "error": result.error,
    }


@router.get("/{app_id}/webhooks/deliveries")
async def list_webhook_deliveries(
    app_id: uuid.UUID,
    db: DBSession,
    current_user: CurrentUser,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    """List webhook delivery attempts for an application."""
    app_repo = SQLTenantApplicationRepository(db)
    app = await app_repo.get_by_id(app_id)
    if not app or app.owner_id != current_user.id:
        raise ApplicationNotFoundError()

    delivery_repo = SQLWebhookDeliveryRepository(db)
    offset = (page - 1) * page_size
    deliveries = await delivery_repo.list_by_app(app_id, offset=offset, limit=page_size)

    return {
        "data": [
            {
                "delivery_id": str(d.id),
                "session_id": str(d.session_id),
                "status": d.status.lower(),
                "attempt_count": d.attempt_count,
                "last_http_status": d.last_status_code,
                "delivered_at": d.delivered_at.isoformat() if d.delivered_at else None,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in deliveries
        ],
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": len(deliveries),
        },
    }


@router.post("/{app_id}/webhooks/deliveries/{delivery_id}/retry", status_code=202)
async def retry_webhook_delivery(
    app_id: uuid.UUID,
    delivery_id: uuid.UUID,
    db: DBSession,
    current_user: CurrentUser,
) -> dict:
    """Manually re-queue a failed webhook delivery."""
    app_repo = SQLTenantApplicationRepository(db)
    app = await app_repo.get_by_id(app_id)
    if not app or app.owner_id != current_user.id:
        raise ApplicationNotFoundError()

    delivery_repo = SQLWebhookDeliveryRepository(db)
    delivery = await delivery_repo.get_by_id(delivery_id)

    if not delivery or delivery.app_id != app_id:
        raise HTTPException(status_code=404, detail="Webhook delivery not found.")

    if delivery.status not in ("FAILED", "DEAD"):
        raise HTTPException(status_code=400, detail="Only failed deliveries can be retried.")

    # Queue re-delivery via Celery
    try:
        from spectre.workers.tasks.webhook_task import deliver_webhook
        deliver_webhook.delay(str(delivery.session_id), str(app_id))
    except Exception:
        raise HTTPException(status_code=503, detail="Worker queue unavailable.")

    return {
        "delivery_id": str(delivery_id),
        "status": "pending",
        "message": "Re-delivery queued.",
    }
