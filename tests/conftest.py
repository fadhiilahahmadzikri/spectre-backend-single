"""Spectre API Test Infrastructure — Shared Fixtures.

Provides:
- Async test client with mocked DB, Redis, and ML models
- JWT-authenticated client fixture (dashboard endpoints)
- API-key-authenticated client fixture (face/ML endpoints)
- Factory helpers for test entities
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest
from httpx import ASGITransport, AsyncClient

from spectre.config import Settings
from spectre.domain.entities.api_key import ApiKey
from spectre.domain.entities.tenant_application import TenantApplication
from spectre.domain.entities.user import User
from spectre.domain.value_objects.face_embedding import FaceEmbedding
from spectre.domain.value_objects.liveness_result import LivenessResult
from spectre.main import create_app


# =============================================================================
# SETTINGS
# =============================================================================


@pytest.fixture
def test_settings() -> Settings:
    """Minimal settings for unit/integration tests — no external deps."""
    return Settings(
        app_env="development",
        debug=True,
        log_enqueue=False,
        database_url="sqlite+aiosqlite:///",
        redis_url="redis://localhost:6379/15",
        jwt_secret_key="test_jwt_secret_64_chars_long_enough_for_hmac_hs256_signing_key",
        encryption_key="dGVzdGtleXRlc3RrZXl0ZXN0a2V5dGVzdGtleTE=",
        bcrypt_cost=4,
        model_path="artifact/best_model.keras",
    )


# =============================================================================
# APPLICATION
# =============================================================================


@pytest.fixture
def app(test_settings: Settings):
    """FastAPI app with mocked infrastructure."""
    application = create_app(settings=test_settings)

    # --- Database (In-memory SQLite with Postgres Compatibility) ---
    from sqlalchemy import StaticPool, event
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    from sqlalchemy.dialects.postgresql import JSONB
    from sqlalchemy.types import JSON
    from spectre.infrastructure.database.base import Base

    # Compatibility: Map JSONB to JSON for SQLite
    @event.listens_for(Base.metadata, "before_create")
    def receive_before_create(target, connection, **kw):
        if connection.dialect.name == "sqlite":
            for table in target.tables.values():
                for column in table.columns:
                    if isinstance(column.type, JSONB):
                        column.type = JSON()

    # We use a custom engine for unit tests to ensure it's in-memory and shared
    engine = create_async_engine(
        test_settings.database_url,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    application.state.db_engine = engine
    application.state.db_session_factory = session_factory

    # Create tables for the in-memory DB
    import asyncio
    async def create_tables():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    
    loop = asyncio.get_event_loop()
    if loop.is_running():
        asyncio.ensure_future(create_tables())
    else:
        loop.run_until_complete(create_tables())

    # --- Redis (Mocked) ---
    mock_redis = AsyncMock()
    mock_redis.ping.return_value = True
    mock_redis.incr.return_value = 1
    mock_redis.ttl.return_value = 60
    mock_redis.close = AsyncMock()
    application.state.redis = mock_redis

    return application


# =============================================================================
# HTTP CLIENTS
# =============================================================================


@pytest.fixture
async def client(app) -> AsyncClient:
    """Unauthenticated async HTTP test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def auth_client(app, test_user) -> AsyncClient:
    """JWT-authenticated client for dashboard endpoints."""
    from spectre.interface.dependencies import get_current_user

    app.dependency_overrides[get_current_user] = lambda: test_user
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": "Bearer fake_test_token"},
    ) as ac:
        yield ac
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
async def api_key_client(app, test_app_entity) -> AsyncClient:
    """API-key-authenticated client for face/ML endpoints."""
    from spectre.interface.dependencies import get_authenticated_app, check_rate_limit

    app.dependency_overrides[get_authenticated_app] = lambda: test_app_entity
    app.dependency_overrides[check_rate_limit] = lambda: None
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"X-API-Key": "spk_test1234567890abcdef"},
    ) as ac:
        yield ac
    app.dependency_overrides.pop(get_authenticated_app, None)
    app.dependency_overrides.pop(check_rate_limit, None)


# =============================================================================
# ENTITY FIXTURES
# =============================================================================


@pytest.fixture
def test_user() -> User:
    """Verified, active test user."""
    return User(
        id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        email="testuser@spectre.io",
        display_name="Test User",
        is_active=True,
        totp_enabled=False,
        totp_secret_encrypted=None,
        created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )


@pytest.fixture
def test_app_entity() -> TenantApplication:
    """Active tenant application for API key auth."""
    return TenantApplication(
        id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
        owner_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        name="Test Application",
        status="active",
        liveness_threshold=0.85,
        similarity_threshold=0.75,
        allowed_ips=None,
        created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )


@pytest.fixture
def test_api_key(test_app_entity) -> ApiKey:
    """Active API key linked to test application."""
    return ApiKey(
        id=uuid.UUID("33333333-3333-3333-3333-333333333333"),
        app_id=test_app_entity.id,
        key_prefix="spk_test1234",
        key_hash="$2b$12$fakehashforkey",
        key_type="legacy",
        status="active",
        last_used_at=None,
        created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        revoked_at=None,
    )


# =============================================================================
# ML MODEL MOCKS
# =============================================================================


@pytest.fixture
def mock_fas_model():
    """FAS model mock — always returns 'live' with high confidence."""
    model = MagicMock()
    model.predict.return_value = LivenessResult.from_probabilities(
        probabilities=[0.01, 0.01, 0.01, 0.01, 0.01, 0.95],
        threshold=0.5,
        inference_time_ms=50,
    )
    model.predict_batch.return_value = model.predict.return_value
    return model


@pytest.fixture
def mock_embedding_model():
    """Embedding model mock — returns deterministic 512-dim vector."""
    model = MagicMock()
    rng = np.random.default_rng(42)
    vec = rng.standard_normal(512).astype(np.float32)
    vec = vec / np.linalg.norm(vec)
    model.extract.return_value = FaceEmbedding.from_list(vec.tolist())
    model.extract_from_bytes.return_value = FaceEmbedding.from_list(vec.tolist())
    return model


@pytest.fixture
def mock_model_registry(mock_fas_model, mock_embedding_model):
    """Complete model registry mock."""
    registry = MagicMock()
    registry.is_loaded.return_value = True
    registry.classify = mock_fas_model.predict
    registry.extract_embedding = mock_embedding_model.extract
    return registry


# =============================================================================
# SAMPLE DATA
# =============================================================================


@pytest.fixture
def sample_user_id() -> uuid.UUID:
    return uuid.UUID("12345678-1234-1234-1234-123456789abc")


@pytest.fixture
def sample_base64_image() -> str:
    """Minimal valid JPEG as base64 (1x1 pixel)."""
    import base64
    # Minimal JPEG: 1x1 white pixel
    jpeg_bytes = bytes([
        0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01,
        0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0xFF, 0xDB, 0x00, 0x43,
        0x00, 0x08, 0x06, 0x06, 0x07, 0x06, 0x05, 0x08, 0x07, 0x07, 0x07, 0x09,
        0x09, 0x08, 0x0A, 0x0C, 0x14, 0x0D, 0x0C, 0x0B, 0x0B, 0x0C, 0x19, 0x12,
        0x13, 0x0F, 0x14, 0x1D, 0x1A, 0x1F, 0x1E, 0x1D, 0x1A, 0x1C, 0x1C, 0x20,
        0x24, 0x2E, 0x27, 0x20, 0x22, 0x2C, 0x23, 0x1C, 0x1C, 0x28, 0x37, 0x29,
        0x2C, 0x30, 0x31, 0x34, 0x34, 0x34, 0x1F, 0x27, 0x39, 0x3D, 0x38, 0x32,
        0x3C, 0x2E, 0x33, 0x34, 0x32, 0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01,
        0x00, 0x01, 0x01, 0x01, 0x11, 0x00, 0xFF, 0xC4, 0x00, 0x1F, 0x00, 0x00,
        0x01, 0x05, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
        0x09, 0x0A, 0x0B, 0xFF, 0xC4, 0x00, 0xB5, 0x10, 0x00, 0x02, 0x01, 0x03,
        0x03, 0x02, 0x04, 0x03, 0x05, 0x05, 0x04, 0x04, 0x00, 0x00, 0x01, 0x7D,
        0xFF, 0xDA, 0x00, 0x08, 0x01, 0x01, 0x00, 0x00, 0x3F, 0x00, 0x7B, 0x94,
        0x11, 0x00, 0x00, 0x00, 0x00, 0x00, 0xFF, 0xD9,
    ])
    return base64.b64encode(jpeg_bytes).decode()
