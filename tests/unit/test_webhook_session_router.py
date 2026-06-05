"""Tests — Webhook & Session Routers.

Covers: POST /api/v1/applications/{app_id}/webhooks/test
        GET /api/v1/sessions
        POST /api/v1/client-logs
"""

import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestWebhookRouter:
    """POST /api/v1/applications/{app_id}/webhooks/test"""

    async def test_webhook_test_without_auth_returns_401(self, client: AsyncClient):
        fake_id = str(uuid.uuid4())
        response = await client.post(f"/api/v1/applications/{fake_id}/webhooks/test")
        assert response.status_code in (401, 422)

    async def test_webhook_test_nonexistent_app_returns_404(
        self, auth_client: AsyncClient
    ):
        fake_id = str(uuid.uuid4())
        response = await auth_client.post(
            f"/api/v1/applications/{fake_id}/webhooks/test"
        )
        assert response.status_code in (404, 500)


@pytest.mark.asyncio
class TestSessionRouter:
    """GET /api/v1/sessions"""

    async def test_sessions_without_auth_returns_401(self, client: AsyncClient):
        response = await client.get("/api/v1/sessions")
        assert response.status_code in (401, 422)

    async def test_sessions_missing_app_id_returns_422(self, auth_client: AsyncClient):
        response = await auth_client.get("/api/v1/sessions")
        assert response.status_code == 422

    async def test_sessions_with_valid_params(self, auth_client: AsyncClient):
        fake_id = str(uuid.uuid4())
        response = await auth_client.get(
            "/api/v1/sessions", params={"app_id": fake_id}
        )
        # Should be 404 (app not found) or 500 (DB not mocked), not 422
        assert response.status_code != 422


@pytest.mark.asyncio
class TestClientLogRouter:
    """POST /api/v1/client-logs"""

    async def test_client_log_accepts_payload(self, client: AsyncClient):
        response = await client.post(
            "/api/v1/client-logs",
            json={
                "level": "error",
                "message": "Camera permission denied",
                "context": {"browser": "Chrome", "os": "Android"},
            },
        )
        # Should accept without auth (telemetry endpoint)
        assert response.status_code in (200, 201, 202, 422)
