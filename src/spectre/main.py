"""Spectre FastAPI application factory.

Uses the factory pattern for clean startup/shutdown lifecycle management.
Model loading, database pool, and Redis connections are managed in the lifespan.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from spectre.config import Settings, get_settings
from spectre.core.logger import get_logger, setup_logging

logger = get_logger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup and shutdown hooks."""
    settings: Settings = app.state.settings

    logger.info(
        "spectre_starting | app_env={} | debug={}",
        settings.app_env,
        settings.debug,
    )

    # --- Database engine + session factory ---
    from spectre.infrastructure.database.base import create_engine_and_session

    engine, session_factory = create_engine_and_session(settings)
    app.state.db_engine = engine
    app.state.db_session_factory = session_factory
    logger.info("database_initialized")

    # --- SQLAlchemy query logging ---
    from spectre.infrastructure.database.query_logger import attach_query_logging

    attach_query_logging(
        engine,
        slow_query_threshold_ms=settings.log_slow_query_ms,
    )

    # --- Redis ---
    from spectre.infrastructure.cache.redis_client import RedisClient

    redis = RedisClient(settings)
    app.state.redis = redis
    logger.info("redis_initialized")

    # --- Sync persisted config from DB into runtime settings ---
    try:
        from sqlalchemy import text

        async with session_factory() as session:
            result = await session.execute(
                text("SELECT key, value, data_type FROM system_config")
            )
            rows = result.mappings().all()

        from spectre.interface.routers.config_router import _SETTINGS_MAP, _cast_value

        for row in rows:
            key = row["key"]
            if key in _SETTINGS_MAP:
                attr = _SETTINGS_MAP[key]
                setattr(settings, attr, _cast_value(row["value"], row["data_type"]))
        logger.info("config_synced_from_db | keys={}", len(rows))
    except Exception as exc:
        logger.warning("config_sync_failed | error={}", exc)

    # --- ML Model Registry (CPU inference) ---
    from spectre.infrastructure.ml.model_registry import ModelRegistry

    registry = ModelRegistry()
    try:
        registry.load(settings)
        app.state.model_registry = registry
        logger.info("ml_model_loaded")
    except FileNotFoundError:
        logger.warning(
            "ml_model_not_found | path={} | Model file missing — face endpoints will fail.",
            settings.model_path_resolved,
        )
        app.state.model_registry = None
    except Exception as exc:
        logger.exception("ml_model_load_failed | error={}", exc)
        app.state.model_registry = None

    # --- FAS Model Registry (multi-model inference) ---
    from spectre.infrastructure.ml.fas_model_registry import FASModelRegistry

    fas_registry = FASModelRegistry()
    try:
        fas_registry.load_all(
            settings,
            shared_antispoofnet_registry=app.state.model_registry,
        )
        app.state.fas_registry = fas_registry
        logger.info(
            "fas_registry_ready | loaded_count={} | active={}",
            fas_registry.loaded_count,
            settings.active_fas_model,
        )
    except Exception as exc:
        logger.exception("fas_registry_load_failed | error={}", exc)
        app.state.fas_registry = None

    # --- InsightFace ArcFace Registry (identity embeddings) ---
    from spectre.infrastructure.ml.insightface_registry import InsightFaceRegistry

    insightface_reg = InsightFaceRegistry()
    try:
        insightface_reg.load(settings)
        app.state.insightface_registry = insightface_reg
        logger.info("insightface_loaded")
    except Exception as exc:
        logger.warning("insightface_load_failed | error={} | Falling back to legacy embeddings.", exc)
        app.state.insightface_registry = None

    # --- Store settings-dependent services ---
    app.state.settings = settings

    logger.info("spectre_ready | port={}", settings.api_port)

    yield

    # --- Shutdown ---
    logger.info("spectre_shutting_down")

    await redis.close()
    logger.info("redis_closed")

    await engine.dispose()
    logger.info("database_closed")


def create_app(settings: Settings | None = None) -> FastAPI:
    """FastAPI application factory.

    Args:
        settings: Optional settings override (for testing).

    Returns:
        Configured FastAPI application instance.
    """
    if settings is None:
        settings = get_settings()

    # --- Logging (must be first) ---
    setup_logging(
        app_name=settings.app_name,
        log_level=settings.log_level,
        is_production=settings.is_production,
        retention=settings.log_retention,
    )

    app = FastAPI(
        title="Spectre API",
        description=(
            "**AI-Powered Facial Authentication Platform — Identity as a Service**\n\n"
            "Spectre provides biometric face authentication via:\n"
            "- **REST API** — Direct integration for server-to-server face operations\n"
            "- **Snap SDK** (`@thewhitenigs/spectre-snap`) — Drop-in React component for "
            "client-side face capture, liveness detection, and identity verification\n\n"
            "### Authentication\n"
            "- **Dashboard endpoints** → JWT Bearer token (`Authorization: Bearer <token>`)\n"
            "- **Face/ML endpoints** → API Key (`X-API-Key: spk_...`)\n\n"
            "### Snap SDK Integration\n"
            "```bash\n"
            "npm install @thewhitenigs/spectre-snap\n"
            "```\n"
            "The SDK handles camera access, face detection, liveness checks, and API "
            "communication. Results are delivered via real-time callbacks; clients can "
            "fetch server-confirmed details through the session lookup endpoint."
        ),
        version="1.1.0",
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
        lifespan=_lifespan,
        openapi_tags=[
            {"name": "Health", "description": "System status, ML model status, and health checks"},
            {"name": "Authentication", "description": "User registration, login, and Google OAuth"},
            {"name": "Applications", "description": "Tenant application and API key management"},
            {"name": "Platform Admin", "description": "Administrative endpoints for platform oversight, user management, and global metrics (requires `admin` role)"},
            {"name": "Face Operations", "description": "Biometric face registration, authentication, and liveness detection. Used by the Snap SDK and direct API consumers."},
            {"name": "Configuration", "description": "Admin system configuration management with hot-reload"},
            {"name": "SDK Integration", "description": "Endpoints consumed by `@thewhitenigs/spectre-snap` — session polling, mode detection, and ML status. See [NPM package](https://www.npmjs.com/package/@thewhitenigs/spectre-snap)."},
            {"name": "Telemetry", "description": "Frontend logging and error ingestion"},
        ]
    )

    # --- Security Schemes (Swagger UI) ---
    from fastapi.openapi.utils import get_openapi

    def custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema
        openapi_schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        openapi_schema["components"]["securitySchemes"] = {
            "BearerAuth": {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
                "description": "Enter JWT token for Dashboard/Tenant endpoints."
            },
            "ApiKeyAuth": {
                "type": "apiKey",
                "in": "header",
                "name": "X-API-Key",
                "description": "Enter API Key for Face/ML operations."
            }
        }
        app.openapi_schema = openapi_schema
        return app.openapi_schema

    app.openapi = custom_openapi

    app.state.settings = settings

    # --- Session Middleware (Required for OAuth state) ---
    from starlette.middleware.sessions import SessionMiddleware
    app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)

    # --- Register OAuth Clients ---
    from spectre.infrastructure.security.oauth_client import register_oauth_clients
    register_oauth_clients(settings)

    # --- CORS ---
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- Middleware (order matters: outermost first) ---
    from spectre.interface.middleware.logging_middleware import LoggingMiddleware
    from spectre.interface.middleware.request_id import RequestIDMiddleware

    # RequestID runs first (outermost), then Logging reads request.state.request_id
    app.add_middleware(LoggingMiddleware)
    app.add_middleware(RequestIDMiddleware)

    # --- Exception Handlers ---
    from spectre.domain.exceptions.base import SpectreError
    from spectre.interface.middleware.exception_handler import spectre_exception_handler
    app.add_exception_handler(SpectreError, spectre_exception_handler)

    # --- Routers ---
    from spectre.interface.routers.health_router import router as health_router
    from spectre.interface.routers.auth_router import router as auth_router
    from spectre.interface.routers.application_router import router as app_router
    from spectre.interface.routers.face_router import router as face_router
    from spectre.interface.routers.session_router import router as session_router
    from spectre.interface.routers.client_log_router import router as client_log_router
    from spectre.interface.routers.config_router import router as config_router
    from spectre.interface.routers.admin_router import router as admin_router

    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(app_router)
    app.include_router(face_router)
    app.include_router(session_router)
    app.include_router(client_log_router)
    app.include_router(config_router)
    app.include_router(admin_router)

    return app
