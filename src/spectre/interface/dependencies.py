"""FastAPI dependency injection — DB sessions, auth, rate limiting.

These Depends() functions wire the infrastructure layer to the routers.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from spectre.config import Settings
from spectre.domain.entities.tenant_application import TenantApplication
from spectre.domain.entities.user import User
from spectre.infrastructure.cache.redis_client import RedisClient
from spectre.infrastructure.security.api_key_generator import ApiKeyGenerator
from spectre.infrastructure.security.jwt_handler import JWTHandler


# =============================================================================
# Settings
# =============================================================================


def get_settings(request: Request) -> Settings:
    """Retrieve Settings from app state."""
    return request.app.state.settings


# =============================================================================
# Database Session
# =============================================================================


async def get_db_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session from the app-scoped session factory."""
    session_factory = request.app.state.db_session_factory
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


DBSession = Annotated[AsyncSession, Depends(get_db_session)]


# =============================================================================
# JWT Bearer Authentication (Dashboard endpoints)
# =============================================================================


async def get_current_user(
    request: Request,
    authorization: str = Header(..., alias="Authorization"),
) -> User:
    """Extract and validate JWT from Authorization header.

    Returns the authenticated User entity.
    Raises 401 if token is missing, malformed, or expired.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error_code": "INVALID_TOKEN", "message": "Missing Bearer prefix."},
        )
    token = authorization[7:]

    settings: Settings = request.app.state.settings
    jwt_handler = JWTHandler(settings)

    try:
        user_id = jwt_handler.get_user_id(token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error_code": "INVALID_TOKEN", "message": "Invalid or expired token."},
        )

    # Load user from DB
    from spectre.infrastructure.repositories.sql_repositories import SQLUserRepository

    session_factory = request.app.state.db_session_factory
    async with session_factory() as session:
        repo = SQLUserRepository(session)
        user = await repo.get_by_id(user_id)

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error_code": "INVALID_TOKEN", "message": "User not found or disabled."},
        )

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


# =============================================================================
# API Key Authentication (ML/Face endpoints)
# =============================================================================


async def get_authenticated_app(
    request: Request,
    x_api_key: str = Header(..., alias="X-API-Key"),
) -> TenantApplication:
    """Validate X-API-Key header and return the associated TenantApplication.

    Raises 401 if key is missing, invalid, revoked, or expired.
    """
    if not x_api_key or len(x_api_key) < 12:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error_code": "INVALID_API_KEY", "message": "Missing or malformed API key."},
        )

    prefix = x_api_key[:12]

    from spectre.infrastructure.repositories.sql_repositories import (
        SQLApiKeyRepository,
        SQLTenantApplicationRepository,
    )

    settings: Settings = request.app.state.settings
    keygen = ApiKeyGenerator(settings)
    session_factory = request.app.state.db_session_factory

    async with session_factory() as session:
        key_repo = SQLApiKeyRepository(session)
        api_key = await key_repo.get_by_prefix(prefix)

        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error_code": "INVALID_API_KEY", "message": "API key not found."},
            )

        if api_key.status not in ("active", "grace_period"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error_code": "INVALID_API_KEY", "message": "API key has been revoked."},
            )

        if not keygen.verify(x_api_key, api_key.key_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error_code": "INVALID_API_KEY", "message": "API key verification failed."},
            )

        # Update last_used_at
        await key_repo.update_last_used(api_key.id)

        # Load the application
        app_repo = SQLTenantApplicationRepository(session)
        app = await app_repo.get_by_id(api_key.app_id)
        await session.commit()

    if not app or app.status != "active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error_code": "INVALID_API_KEY", "message": "Application is not active."},
        )

    return app


AuthenticatedApp = Annotated[TenantApplication, Depends(get_authenticated_app)]


# =============================================================================
# Rate Limiting
# =============================================================================


async def check_rate_limit(
    request: Request,
    x_api_key: str = Header(None, alias="X-API-Key"),
) -> None:
    """Redis-backed rate limiting: 60 requests/minute per API key.

    Raises 429 Too Many Requests if limit exceeded.
    """
    if not x_api_key:
        return  # No API key = no rate limit (JWT endpoints have their own)

    redis: RedisClient | None = getattr(request.app.state, "redis", None)
    if not redis:
        return  # Redis not initialized (testing)

    rate_key = f"rate:{x_api_key[:12]}"
    count = await redis.incr(rate_key)

    if count == 1:
        # First request in window — set 60-second expiry
        await redis.expire(rate_key, 60)

    if count > 60:
        ttl = await redis.ttl(rate_key)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error_code": "RATE_LIMIT_EXCEEDED",
                "message": "60 requests/minute limit exceeded.",
            },
            headers={"Retry-After": str(max(ttl, 1))},
        )
