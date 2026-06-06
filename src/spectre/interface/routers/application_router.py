"""Application & API key router — tenant CRUD + API key lifecycle.

All endpoints from API_SPECIFICATION.md §4.3 and §4.4.
All require JWT Bearer authentication.
"""

from __future__ import annotations

import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException

from spectre.config import Settings
from spectre.domain.entities.api_key import ApiKey
from spectre.domain.entities.tenant_application import TenantApplication
from spectre.domain.exceptions.tenant_exceptions import ApplicationNotFoundError
from spectre.interface.dependencies import CurrentUser, DBSession, get_settings
from spectre.interface.schemas.application_schema import (
    ApiKeyCreatedResponse,
    ApplicationResponse,
    CreateApplicationRequest,
    UpdateApplicationRequest,
)
from spectre.infrastructure.repositories.sql_repositories import (
    SQLApiKeyRepository,
    SQLTenantApplicationRepository,
)
from spectre.infrastructure.security.api_key_generator import ApiKeyGenerator

router = APIRouter(prefix="/api/v1/applications", tags=["Applications"])


# =============================================================================
# Application CRUD
# =============================================================================


def _app_to_response(app: TenantApplication) -> dict:
    """Map domain entity to response dict."""
    return {
        "id": str(app.id),
        "name": app.name,
        "status": app.status,
        "liveness_threshold": app.liveness_threshold,
        "similarity_threshold": getattr(app, "similarity_threshold", 0.75),
        "allowed_ips": app.allowed_ips or [],
        "created_at": app.created_at.isoformat() if app.created_at else None,
        "updated_at": app.updated_at.isoformat() if app.updated_at else None,
    }


@router.post("", status_code=201, response_model=ApplicationResponse)
async def create_application(
    body: CreateApplicationRequest,
    db: DBSession,
    current_user: CurrentUser,
    settings: Settings = Depends(get_settings),
) -> dict:
    """Create a new tenant application."""
    app_repo = SQLTenantApplicationRepository(db)

    new_app = TenantApplication(
        id=uuid.uuid4(),
        owner_id=current_user.id,
        name=body.name,
        status="active",
        liveness_threshold=settings.liveness_threshold,
        similarity_threshold=getattr(settings, "similarity_threshold", 0.75),
        created_at=datetime.datetime.now(datetime.timezone.utc),
        updated_at=datetime.datetime.now(datetime.timezone.utc),
    )
    new_app = await app_repo.create(new_app)

    return _app_to_response(new_app)


@router.get("", response_model=dict) # Pagination wrapper
async def list_applications(
    db: DBSession,
    current_user: CurrentUser,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """List all non-deleted applications owned by the authenticated user."""
    app_repo = SQLTenantApplicationRepository(db)
    offset = (page - 1) * page_size
    apps = await app_repo.list_by_owner(current_user.id, offset=offset, limit=page_size)
    return {
        "data": [_app_to_response(a) for a in apps],
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": len(apps),
        },
    }


@router.get("/{app_id}", response_model=ApplicationResponse)
async def get_application(
    app_id: uuid.UUID,
    db: DBSession,
    current_user: CurrentUser,
) -> dict:
    """Get a single application by ID."""
    app_repo = SQLTenantApplicationRepository(db)
    app = await app_repo.get_by_id(app_id)
    if not app or app.owner_id != current_user.id:
        raise ApplicationNotFoundError()
    return _app_to_response(app)


@router.patch("/{app_id}", response_model=ApplicationResponse)
async def update_application(
    app_id: uuid.UUID,
    body: UpdateApplicationRequest,
    db: DBSession,
    current_user: CurrentUser,
) -> dict:
    """Update application settings."""
    app_repo = SQLTenantApplicationRepository(db)

    app = await app_repo.get_by_id(app_id)
    if not app or app.owner_id != current_user.id:
        raise ApplicationNotFoundError()

    if body.name is not None:
        app.name = body.name

    if body.liveness_threshold is not None:
        app.liveness_threshold = body.liveness_threshold
    if body.similarity_threshold is not None:
        app.similarity_threshold = body.similarity_threshold
    if body.allowed_ips is not None:
        app.allowed_ips = body.allowed_ips

    app.updated_at = datetime.datetime.now(datetime.timezone.utc)
    await app_repo.update(app)
    return _app_to_response(app)


@router.delete("/{app_id}", status_code=204)
async def delete_application(
    app_id: uuid.UUID,
    db: DBSession,
    current_user: CurrentUser,
) -> None:
    """Soft-delete an application."""
    app_repo = SQLTenantApplicationRepository(db)
    app = await app_repo.get_by_id(app_id)
    if not app or app.owner_id != current_user.id:
        raise ApplicationNotFoundError()
    await app_repo.soft_delete(app_id)
    return None


# =============================================================================
# API Key Management (nested under /applications/{app_id}/api-keys)
# =============================================================================


@router.post("/{app_id}/api-keys", status_code=201, response_model=ApiKeyCreatedResponse)
async def generate_api_key(
    app_id: uuid.UUID,
    db: DBSession,
    current_user: CurrentUser,
    settings: Settings = Depends(get_settings),
) -> dict:
    """Generate a new API key for the application."""
    app_repo = SQLTenantApplicationRepository(db)
    key_repo = SQLApiKeyRepository(db)

    app = await app_repo.get_by_id(app_id)
    if not app or app.owner_id != current_user.id:
        raise ApplicationNotFoundError()

    keygen = ApiKeyGenerator(settings)
    key_pair = keygen.generate()

    new_key = ApiKey(
        id=uuid.uuid4(),
        app_id=app_id,
        key_prefix=key_pair.prefix,
        key_hash=key_pair.key_hash,
        status="active",
        created_at=datetime.datetime.now(datetime.timezone.utc),
    )
    new_key = await key_repo.create(new_key)

    return {
        "id": str(new_key.id),
        "key_prefix": new_key.key_prefix,
        "full_key": key_pair.full_key,
        "label": None,
        "status": "active",
        "last_used_at": None,
        "created_at": new_key.created_at.isoformat() if new_key.created_at else None,
    }


@router.get("/{app_id}/api-keys", response_model=dict)
async def list_api_keys(
    app_id: uuid.UUID,
    db: DBSession,
    current_user: CurrentUser,
) -> dict:
    """List all API keys for an application."""
    app_repo = SQLTenantApplicationRepository(db)
    key_repo = SQLApiKeyRepository(db)

    app = await app_repo.get_by_id(app_id)
    if not app or app.owner_id != current_user.id:
        raise ApplicationNotFoundError()

    keys = await key_repo.list_by_app(app_id)
    return {
        "data": [
            {
                "id": str(k.id),
                "key_prefix": k.key_prefix,
                "label": getattr(k, "label", None),
                "status": k.status,
                "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
                "created_at": k.created_at.isoformat() if k.created_at else None,
            }
            for k in keys
        ],
    }


@router.post("/{app_id}/api-keys/{key_id}/revoke", status_code=204)
async def revoke_api_key(
    app_id: uuid.UUID,
    key_id: uuid.UUID,
    db: DBSession,
    current_user: CurrentUser,
) -> None:
    """Soft-revoke an API key.

    Sets status='revoked' and timestamps revoked_at. The row is preserved for
    audit trail; the key can never be used again (middleware rejects revoked
    keys) and cannot be reactivated. Use DELETE to permanently remove the row.
    """
    app_repo = SQLTenantApplicationRepository(db)
    key_repo = SQLApiKeyRepository(db)

    app = await app_repo.get_by_id(app_id)
    if not app or app.owner_id != current_user.id:
        raise ApplicationNotFoundError()

    key = await key_repo.get_by_id(key_id)
    if not key or key.app_id != app_id:
        raise HTTPException(status_code=404, detail="API key not found.")

    await key_repo.revoke(key_id)
    return None


@router.delete("/{app_id}/api-keys/{key_id}", status_code=204)
async def delete_api_key(
    app_id: uuid.UUID,
    key_id: uuid.UUID,
    db: DBSession,
    current_user: CurrentUser,
) -> None:
    """Hard-delete an API key row.

    Permanent: the row is removed from the database. Use this to clean up
    keys that were generated by mistake, never used, or revoked and no
    longer needed in the dashboard.
    """
    app_repo = SQLTenantApplicationRepository(db)
    key_repo = SQLApiKeyRepository(db)

    app = await app_repo.get_by_id(app_id)
    if not app or app.owner_id != current_user.id:
        raise ApplicationNotFoundError()

    key = await key_repo.get_by_id(key_id)
    if not key or key.app_id != app_id:
        raise HTTPException(status_code=404, detail="API key not found.")

    await key_repo.delete(key_id)
    return None
