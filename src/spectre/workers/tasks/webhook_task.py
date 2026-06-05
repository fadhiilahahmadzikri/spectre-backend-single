"""Webhook delivery task — exponential backoff retry with max 4 attempts.

Picks up a delivery job from the Redis queue, loads session/app from DB,
signs the payload with the tenant's webhook secret, and dispatches via HTTP.
"""

from __future__ import annotations

import asyncio
import datetime
import json
import uuid
from typing import Any

from spectre.core.logger import get_logger
from spectre.workers.celery_app import celery_app

logger = get_logger(__name__)


def _build_webhook_payload(session, app_id: str) -> dict[str, Any]:
    """Build the webhook payload from a session entity."""
    event_map = {
        "REGISTERED": "face.registered",
        "AUTHENTICATED": "face.authenticated",
        "REJECTED": "face.no_match",
        "SPOOF_DETECTED": "face.spoof_rejected",
        "FAILED": "face.failed",
    }

    payload: dict[str, Any] = {
        "event": event_map.get(session.status, f"face.{session.status.lower()}"),
        "session_id": str(session.id),
        "app_id": app_id,
        "external_user_id": session.external_user_id,
        "status": session.status.lower(),
        "liveness_class": session.liveness_class,
        "liveness_confidence": session.liveness_confidence,
        "inference_time_ms": session.inference_time_ms,
        "timestamp": (
            session.completed_at.isoformat()
            if session.completed_at
            else datetime.datetime.now(datetime.timezone.utc).isoformat()
        ),
    }

    # Include similarity fields for authentication sessions
    if session.session_type == "authentication":
        payload["match"] = session.status == "AUTHENTICATED"
        payload["similarity_score"] = session.similarity_score

    return payload


def _run_async(coro):
    """Run an async coroutine in Celery's sync worker context."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, coro).result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


async def _deliver(session_id: str, app_id: str) -> dict:
    """Async delivery logic — loads from DB, signs, dispatches."""
    from spectre.config import get_settings
    from spectre.infrastructure.database.base import create_engine_and_session
    from spectre.infrastructure.repositories.sql_repositories import (
        SQLAuthSessionRepository,
        SQLTenantApplicationRepository,
        SQLWebhookDeliveryRepository,
    )
    from spectre.infrastructure.security.aes_encryption import AESEncryption
    from spectre.infrastructure.webhook.hmac_signer import HMACSigner
    from spectre.infrastructure.webhook.http_dispatcher import WebhookDispatcher
    from spectre.domain.entities.webhook_delivery import WebhookDelivery

    settings = get_settings()
    engine, session_factory = create_engine_and_session(settings)

    try:
        async with session_factory() as db:
            session_repo = SQLAuthSessionRepository(db)
            app_repo = SQLTenantApplicationRepository(db)

            session = await session_repo.get_by_id(uuid.UUID(session_id))
            if not session:
                return {"status": "skipped", "reason": "session_not_found"}

            app = await app_repo.get_by_id(uuid.UUID(app_id))
            if not app or not app.has_webhook:
                return {"status": "skipped", "reason": "no_webhook_configured"}

            # Build payload
            payload = _build_webhook_payload(session, app_id)

            # Decrypt webhook secret
            encryption = AESEncryption(settings)
            webhook_secret = encryption.decrypt_string(app.webhook_secret_encrypted)

            # Sign and dispatch
            dispatcher = WebhookDispatcher(settings)
            result = await dispatcher.deliver(app.webhook_url, payload, webhook_secret)

            # Record delivery
            delivery_repo = SQLWebhookDeliveryRepository(db)
            delivery = WebhookDelivery(
                id=uuid.uuid4(),
                session_id=uuid.UUID(session_id),
                app_id=uuid.UUID(app_id),
                status="DELIVERED" if result.success else "FAILED",
                attempt_count=1,
                last_status_code=result.status_code,
                last_error=result.error,
                payload_hash=HMACSigner.payload_hash(payload),
                delivered_at=(
                    datetime.datetime.now(datetime.timezone.utc) if result.success else None
                ),
            )
            await delivery_repo.create(delivery)
            await db.commit()

            if not result.success:
                raise RuntimeError(f"Webhook delivery failed: {result.error}")

            return {"status": "delivered", "session_id": session_id}
    finally:
        await engine.dispose()


@celery_app.task(
    bind=True,
    name="spectre.workers.tasks.webhook_task.deliver_webhook",
    max_retries=4,
    acks_late=True,
    default_retry_delay=30,
)
def deliver_webhook(self, session_id: str, app_id: str) -> dict:
    """Deliver a webhook payload for a completed session.

    Retry strategy: exponential backoff (30s, 60s, 120s, 240s).
    After 4 failures, marks delivery as DEAD.

    Args:
        session_id: UUID string of the auth session.
        app_id: UUID string of the tenant application.

    Returns:
        Dict with delivery status.
    """
    try:
        logger.info(
            "webhook_delivery_attempt",
            session_id=session_id,
            app_id=app_id,
            attempt=self.request.retries + 1,
        )

        result = _run_async(_deliver(session_id, app_id))
        return result

    except Exception as exc:
        backoff = 30 * (2 ** self.request.retries)
        logger.warning(
            "webhook_delivery_retry",
            session_id=session_id,
            attempt=self.request.retries + 1,
            backoff_seconds=backoff,
            error=str(exc),
        )
        raise self.retry(exc=exc, countdown=backoff)
