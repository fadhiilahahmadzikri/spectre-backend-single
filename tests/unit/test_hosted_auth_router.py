from __future__ import annotations

import datetime
import uuid

import pytest
from httpx import AsyncClient

from spectre.domain.entities.api_key import ApiKey
from spectre.domain.entities.auth_session import AuthSession
from spectre.domain.entities.tenant_application import TenantApplication
from spectre.infrastructure.repositories.sql_repositories import (
    SQLApiKeyRepository,
    SQLAuthSessionRepository,
    SQLTenantApplicationRepository,
)
from spectre.infrastructure.security.api_key_generator import ApiKeyGenerator
from spectre.infrastructure.security.hosted_auth import hash_token, utcnow


HOSTED_APP_ID = uuid.UUID("aaaaaaaa-2222-4222-8222-aaaaaaaaaaaa")
HOSTED_OWNER_ID = uuid.UUID("bbbbbbbb-1111-4111-8111-bbbbbbbbbbbb")


@pytest.mark.asyncio
async def test_create_hosted_session_is_idempotent(client: AsyncClient, app):
    secret_key = await _seed_secret_key(app)
    payload = {
        "external_user_id": "user_123",
        "mode": "authenticate",
        "return_url": "https://client.example.com/api/spectre/callback",
        "cancel_url": "https://client.example.com/login",
    }

    first = await client.post(
        "/api/v1/hosted/auth-sessions",
        headers={"X-Spectre-Secret-Key": secret_key, "Idempotency-Key": "login-user-123"},
        json=payload,
    )
    assert first.status_code == 201
    first_body = first.json()

    second = await client.post(
        "/api/v1/hosted/auth-sessions",
        headers={"X-Spectre-Secret-Key": secret_key, "Idempotency-Key": "login-user-123"},
        json=payload,
    )
    assert second.status_code == 201
    second_body = second.json()
    assert second_body["id"] == first_body["id"]
    assert second_body["client_secret"] == first_body["client_secret"]

    bootstrap = await client.get(
        f"/api/v1/hosted/auth-sessions/{first_body['id']}/bootstrap",
        params={"client_secret": first_body["client_secret"]},
    )
    assert bootstrap.status_code == 200
    assert bootstrap.json()["ui"]["show_config_button"] is False


@pytest.mark.asyncio
async def test_hosted_session_rejects_unallowed_return_origin(client: AsyncClient, app):
    secret_key = await _seed_secret_key(app)
    response = await client.post(
        "/api/v1/hosted/auth-sessions",
        headers={"X-Spectre-Secret-Key": secret_key},
        json={
            "external_user_id": "user_123",
            "mode": "authenticate",
            "return_url": "https://evil.example.com/callback",
            "cancel_url": "https://client.example.com/login",
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"]["error_code"] == "REDIRECT_ORIGIN_NOT_ALLOWED"


@pytest.mark.asyncio
async def test_secret_key_dependency_rejects_legacy_key(client: AsyncClient, app):
    legacy_key = await _seed_legacy_key(app)
    response = await client.post(
        "/api/v1/hosted/auth-sessions",
        headers={"X-Spectre-Secret-Key": legacy_key},
        json={
            "external_user_id": "user_123",
            "mode": "authenticate",
            "return_url": "https://client.example.com/callback",
            "cancel_url": "https://client.example.com/login",
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_exchange_code_is_one_time(client: AsyncClient, app):
    secret_key = await _seed_secret_key(app)
    session_id = await _seed_exchangeable_session(app)

    first = await client.post(
        f"/api/v1/hosted/auth-sessions/{session_id}/exchange",
        headers={"X-Spectre-Secret-Key": secret_key},
        json={"code": "hex_test_code"},
    )
    assert first.status_code == 200
    assert first.json()["status"] == "authenticated"

    second = await client.post(
        f"/api/v1/hosted/auth-sessions/{session_id}/exchange",
        headers={"X-Spectre-Secret-Key": secret_key},
        json={"code": "hex_test_code"},
    )
    assert second.status_code == 409
    assert second.json()["detail"]["error_code"] == "EXCHANGE_CODE_USED"


@pytest.mark.asyncio
async def test_jwks_does_not_expose_hmac_secret(client: AsyncClient):
    response = await client.get("/.well-known/jwks.json")
    assert response.status_code == 200
    assert response.json() == {"keys": []}


async def _seed_secret_key(app) -> str:
    return await _seed_api_key(app, "secret")


async def _seed_legacy_key(app) -> str:
    return await _seed_api_key(app, "legacy")


async def _seed_api_key(app, key_type: str) -> str:
    settings = app.state.settings
    key_pair = ApiKeyGenerator(settings).generate_for_type(key_type)
    app_id = HOSTED_APP_ID
    async with app.state.db_session_factory() as session:
        app_repo = SQLTenantApplicationRepository(session)
        if await app_repo.get_by_id(app_id) is None:
            await app_repo.create(
                TenantApplication(
                    id=app_id,
                    owner_id=HOSTED_OWNER_ID,
                    name="Hosted Test App",
                    allowed_origins=["https://client.example.com"],
                )
            )
        await SQLApiKeyRepository(session).create(
            ApiKey(
                id=uuid.uuid4(),
                app_id=app_id,
                key_prefix=key_pair.prefix,
                key_hash=key_pair.key_hash,
                key_type=key_type,
            )
        )
        await session.commit()
    return key_pair.full_key


async def _seed_exchangeable_session(app) -> uuid.UUID:
    settings = app.state.settings
    session_id = uuid.UUID("cccccccc-5555-4555-8555-cccccccccccc")
    now = utcnow()
    async with app.state.db_session_factory() as session:
        repo = SQLAuthSessionRepository(session)
        await repo.create(
            AuthSession(
                id=session_id,
                app_id=HOSTED_APP_ID,
                session_type="hosted_auth",
                status="AUTHENTICATED",
                lifecycle_state="SUCCEEDED",
                external_user_id="user_123",
                client_secret_hash=hash_token("hcs_test", settings),
                exchange_code_hash=hash_token("hex_test_code", settings),
                exchange_code_expires_at=now + datetime.timedelta(minutes=5),
                return_url="https://client.example.com/callback",
                cancel_url="https://client.example.com/login",
                client_metadata={"mode": "authenticate"},
                created_at=now,
                completed_at=now,
            )
        )
        await session.commit()
    return session_id
