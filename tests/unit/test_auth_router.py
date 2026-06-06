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


@pytest.mark.asyncio
class TestGoogleOAuthCallback:
    """GET /api/v1/auth/oauth/google/callback"""

    async def test_google_callback_not_configured_redirects(self, client: AsyncClient):
        response = await client.get("/api/v1/auth/oauth/google/callback", follow_redirects=False)
        assert response.status_code == 307
        location = response.headers.get("location")
        assert location is not None
        assert "error=OAUTH_CONFIG_ERROR" in location
        assert "Google+OAuth+is+not+configured+on+this+server" in location

    async def test_google_callback_state_mismatch_redirects(self, client: AsyncClient, app):
        from unittest.mock import patch
        from spectre.config import Settings, get_settings

        custom_settings = Settings(
            app_env="development",
            debug=True,
            database_url="sqlite+aiosqlite:///",
            redis_url="redis://localhost:6379/15",
            jwt_secret_key="test_jwt_secret_64_chars_long_enough_for_hmac_256_signing_key",
            encryption_key="dGVzdGtleXRlc3RrZXl0ZXN0a2V5dGVzdGtleTE=",
            model_path="artifact/best_model.keras",
            google_client_id="dummy_client_id",
            google_client_secret="dummy_client_secret",
            oauth_frontend_redirect="http://dummy-frontend",
        )
        app.dependency_overrides[get_settings] = lambda: custom_settings

        with patch("spectre.infrastructure.security.oauth_client.oauth.google.authorize_access_token") as mock_auth:
            mock_auth.side_effect = Exception("mismatching_state")
            try:
                response = await client.get("/api/v1/auth/oauth/google/callback", follow_redirects=False)
                assert response.status_code == 307
                location = response.headers.get("location")
                assert location is not None
                assert "http://dummy-frontend/oauth/callback" in location
                assert "error=OAUTH_STATE_MISMATCH" in location
            finally:
                app.dependency_overrides.pop(get_settings, None)

    async def test_google_callback_other_exception_redirects(self, client: AsyncClient, app):
        from unittest.mock import patch
        from spectre.config import Settings, get_settings

        custom_settings = Settings(
            app_env="development",
            debug=True,
            database_url="sqlite+aiosqlite:///",
            redis_url="redis://localhost:6379/15",
            jwt_secret_key="test_jwt_secret_64_chars_long_enough_for_hmac_256_signing_key",
            encryption_key="dGVzdGtleXRlc3RrZXl0ZXN0a2V5dGVzdGtleTE=",
            model_path="artifact/best_model.keras",
            google_client_id="dummy_client_id",
            google_client_secret="dummy_client_secret",
            oauth_frontend_redirect="http://dummy-frontend",
        )
        app.dependency_overrides[get_settings] = lambda: custom_settings

        with patch("spectre.infrastructure.security.oauth_client.oauth.google.authorize_access_token") as mock_auth:
            mock_auth.side_effect = Exception("Some random API error")
            try:
                response = await client.get("/api/v1/auth/oauth/google/callback", follow_redirects=False)
                assert response.status_code == 307
                location = response.headers.get("location")
                assert location is not None
                assert "http://dummy-frontend/oauth/callback" in location
                assert "error=OAUTH_FAILED" in location
                assert "Some+random+API+error" in location
            finally:
                app.dependency_overrides.pop(get_settings, None)
