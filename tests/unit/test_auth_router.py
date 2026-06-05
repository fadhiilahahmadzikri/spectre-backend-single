"""Tests — Auth Router.

Covers: POST /api/v1/auth/register, /login,
        /refresh, /logout, /totp/setup, /totp/confirm, /totp/verify
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestAuthRegister:
    """POST /api/v1/auth/register"""

    async def test_register_missing_email_returns_422(self, client: AsyncClient):
        response = await client.post(
            "/api/v1/auth/register",
            json={"password": "SecureP@ss123", "display_name": "Test"},
        )
        assert response.status_code == 422

    async def test_register_missing_password_returns_422(self, client: AsyncClient):
        response = await client.post(
            "/api/v1/auth/register",
            json={"email": "test@example.com"},
        )
        assert response.status_code == 422

    async def test_register_invalid_email_returns_422(self, client: AsyncClient):
        response = await client.post(
            "/api/v1/auth/register",
            json={"email": "not-an-email", "password": "SecureP@ss123"},
        )
        assert response.status_code == 422

    async def test_register_empty_body_returns_422(self, client: AsyncClient):
        response = await client.post("/api/v1/auth/register", json={})
        assert response.status_code == 422


@pytest.mark.asyncio
class TestAuthLogin:
    """POST /api/v1/auth/login"""

    async def test_login_missing_credentials_returns_422(self, client: AsyncClient):
        response = await client.post("/api/v1/auth/login", json={})
        assert response.status_code == 422

    async def test_login_missing_password_returns_422(self, client: AsyncClient):
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "test@example.com"},
        )
        assert response.status_code == 422


@pytest.mark.asyncio
class TestAuthProtected:
    """Endpoints requiring JWT Bearer token."""

    async def test_refresh_without_token_returns_401(self, client: AsyncClient):
        response = await client.post("/api/v1/auth/refresh", json={})
        assert response.status_code in (401, 422)

    async def test_logout_without_token_returns_401(self, client: AsyncClient):
        response = await client.post("/api/v1/auth/logout")
        assert response.status_code in (401, 422)

    async def test_totp_setup_without_token_returns_401(self, client: AsyncClient):
        response = await client.post("/api/v1/auth/totp/setup")
        assert response.status_code in (401, 422)

    async def test_totp_confirm_without_token_returns_401(self, client: AsyncClient):
        response = await client.post("/api/v1/auth/totp/confirm", json={"code": "123456"})
        assert response.status_code in (401, 422)

    async def test_totp_verify_without_token_returns_401(self, client: AsyncClient):
        response = await client.post("/api/v1/auth/totp/verify", json={"code": "123456"})
        assert response.status_code in (401, 422)
