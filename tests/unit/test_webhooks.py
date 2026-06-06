from __future__ import annotations

import uuid

import pytest

from spectre.infrastructure.repositories.sql_repositories import SQLWebhookRepository
from spectre.infrastructure.security.webhook_signature import (
    sign_webhook_payload,
    verify_webhook_signature,
)


def test_webhook_signature_verifies_current_payload():
    body = b'{"id":"evt_test"}'
    secret = "whsec_test"
    signature = sign_webhook_payload(body, secret, timestamp=1000)

    assert verify_webhook_signature(
        body,
        signature,
        secret,
        tolerance_seconds=300,
        now=1005,
    )


def test_webhook_signature_rejects_replay_timestamp():
    body = b'{"id":"evt_test"}'
    secret = "whsec_test"
    signature = sign_webhook_payload(body, secret, timestamp=1000)

    assert not verify_webhook_signature(
        body,
        signature,
        secret,
        tolerance_seconds=300,
        now=1401,
    )


@pytest.mark.asyncio
async def test_webhook_event_recording_is_idempotent(app):
    app_id = uuid.UUID("aaaaaaaa-2222-4222-8222-aaaaaaaaaaaa")
    async with app.state.db_session_factory() as session:
        repo = SQLWebhookRepository(session)
        _, inserted = await repo.record_event(
            event_id="evt_duplicate",
            app_id=app_id,
            event_type="auth_session.succeeded",
            payload={"id": "evt_duplicate"},
        )
        _, duplicate_inserted = await repo.record_event(
            event_id="evt_duplicate",
            app_id=app_id,
            event_type="auth_session.succeeded",
            payload={"id": "evt_duplicate"},
        )
        await session.commit()

    assert inserted is True
    assert duplicate_inserted is False
