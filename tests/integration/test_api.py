"""Integration tests — API endpoint smoke tests.

These test that routers are properly wired, schemas validate,
and the DI chain resolves without errors.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    """Health endpoint returns 200 with component statuses."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "spectre-api"
    assert data["version"] == "0.1.0"
    assert "status" in data
    assert "components" in data
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_register_requires_email_and_password(client: AsyncClient):
    """Registration endpoint validates required fields."""
    # Missing password
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": "test@example.com"},
    )
    assert response.status_code == 422

    # Missing email
    response = await client.post(
        "/api/v1/auth/register",
        json={"password": "Test1234!"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_login_requires_credentials(client: AsyncClient):
    """Login endpoint validates required fields."""
    response = await client.post(
        "/api/v1/auth/login",
        json={},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_face_register_requires_api_key(client: AsyncClient):
    """Face register endpoint requires X-API-Key header."""
    response = await client.post(
        "/api/v1/faces/register",
        json={
            "external_user_id": "usr_test",
            "image": "base64placeholder",
        },
    )
    # Should be 401 (missing API key) or 422 (validation)
    assert response.status_code in (401, 422)


@pytest.mark.asyncio
async def test_application_crud_requires_auth(client: AsyncClient):
    """Application endpoints require JWT Bearer token."""
    response = await client.get("/api/v1/applications")
    assert response.status_code in (401, 422)


@pytest.mark.asyncio
async def test_session_list_requires_auth(client: AsyncClient):
    """Session listing requires JWT + app_id."""
    response = await client.get("/api/v1/sessions")
    assert response.status_code in (401, 422)


@pytest.mark.asyncio
async def test_docs_available_in_debug(client: AsyncClient):
    """OpenAPI docs available in debug mode."""
    response = await client.get("/docs")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_nonexistent_endpoint_returns_404(client: AsyncClient):
    """Unknown endpoints return 404."""
    response = await client.get("/api/v1/nonexistent")
    assert response.status_code in (404, 405)
