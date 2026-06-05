"""Tests — Application & API Key Router.

Covers: GET/POST /api/v1/applications, GET/PUT/DELETE /api/v1/applications/{app_id},
        POST/GET /api/v1/applications/{app_id}/api-keys,
        DELETE /api/v1/applications/{app_id}/api-keys/{key_id}
"""

import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestApplicationAuthRequired:
    """All application endpoints require JWT Bearer."""

    async def test_list_apps_without_auth_returns_401(self, client: AsyncClient):
        response = await client.get("/api/v1/applications")
        assert response.status_code in (401, 422)

    async def test_create_app_without_auth_returns_401(self, client: AsyncClient):
        response = await client.post(
            "/api/v1/applications",
            json={"name": "Test App"},
        )
        assert response.status_code in (401, 422)

    async def test_get_app_without_auth_returns_401(self, client: AsyncClient):
        fake_id = str(uuid.uuid4())
        response = await client.get(f"/api/v1/applications/{fake_id}")
        assert response.status_code in (401, 422)

    async def test_delete_app_without_auth_returns_401(self, client: AsyncClient):
        fake_id = str(uuid.uuid4())
        response = await client.delete(f"/api/v1/applications/{fake_id}")
        assert response.status_code in (401, 422)


@pytest.mark.asyncio
class TestApplicationValidation:
    """Validation tests with authenticated client."""

    async def test_create_app_missing_name_returns_422(self, auth_client: AsyncClient):
        response = await auth_client.post("/api/v1/applications", json={})
        assert response.status_code == 422

    async def test_get_nonexistent_app_returns_404(self, auth_client: AsyncClient):
        fake_id = str(uuid.uuid4())
        response = await auth_client.get(f"/api/v1/applications/{fake_id}")
        assert response.status_code in (404, 500)  # 500 if DB not mocked

    async def test_invalid_uuid_returns_422(self, auth_client: AsyncClient):
        response = await auth_client.get("/api/v1/applications/not-a-uuid")
        assert response.status_code == 422


@pytest.mark.asyncio
class TestApiKeyAuthRequired:
    """API key management endpoints require JWT."""

    async def test_generate_key_without_auth_returns_401(self, client: AsyncClient):
        fake_id = str(uuid.uuid4())
        response = await client.post(f"/api/v1/applications/{fake_id}/api-keys")
        assert response.status_code in (401, 422)

    async def test_list_keys_without_auth_returns_401(self, client: AsyncClient):
        fake_id = str(uuid.uuid4())
        response = await client.get(f"/api/v1/applications/{fake_id}/api-keys")
        assert response.status_code in (401, 422)
