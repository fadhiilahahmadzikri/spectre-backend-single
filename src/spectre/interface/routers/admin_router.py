"""Admin router — full CRUD for users, applications, API keys, face profiles, sessions.

All endpoints require JWT Bearer authentication with role='admin'.
Paginated with ?page=1&page_size=20 query params.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, update, delete

from spectre.interface.dependencies import CurrentUser, DBSession, get_settings
from spectre.config import Settings
from spectre.infrastructure.database.models.tables import (
    ApiKeyModel,
    AuthSessionModel,
    FaceProfileModel,
    TenantApplicationModel,
    UserModel,
)
from spectre.infrastructure.repositories.sql_repositories import (
    SQLApiKeyRepository,
    SQLAuthSessionRepository,
    SQLFaceProfileRepository,
    SQLTenantApplicationRepository,
    SQLUserRepository,
)

router = APIRouter(prefix="/admin", tags=["Admin"])


def _require_admin(user):
    """Raise 403 if user is not admin."""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")


def _paginate(page: int, page_size: int) -> tuple[int, int]:
    """Return (offset, limit) from page params."""
    return (page - 1) * page_size, page_size


# =============================================================================
# Users
# =============================================================================


@router.get("/users")
async def list_users(
    db: DBSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> dict:
    """List all users with pagination."""
    _require_admin(current_user)
    offset, limit = _paginate(page, page_size)

    total_q = await db.execute(select(func.count(UserModel.id)))
    total = total_q.scalar() or 0

    stmt = (
        select(UserModel)
        .order_by(UserModel.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()

    return {
        "data": [
            {
                "id": str(u.id),
                "email": u.email,
                "display_name": u.display_name,
                "role": u.role,
                "is_active": u.is_active,
                "totp_enabled": u.totp_enabled,
                "created_at": u.created_at.isoformat() if u.created_at else None,
                "updated_at": u.updated_at.isoformat() if u.updated_at else None,
            }
            for u in rows
        ],
        "pagination": {"page": page, "page_size": page_size, "total": total},
    }


@router.get("/users/{user_id}")
async def get_user(
    user_id: uuid.UUID,
    db: DBSession,
    current_user: CurrentUser,
) -> dict:
    """Get a single user by ID."""
    _require_admin(current_user)
    repo = SQLUserRepository(db)
    user = await repo.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "id": str(user.id),
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role,
        "is_active": user.is_active,
        "totp_enabled": user.totp_enabled,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "updated_at": user.updated_at.isoformat() if user.updated_at else None,
    }


@router.patch("/users/{user_id}")
async def update_user(
    user_id: uuid.UUID,
    db: DBSession,
    current_user: CurrentUser,
    body: dict[str, Any] = {},
) -> dict:
    """Update a user (role, display_name, is_active, totp_enabled)."""
    _require_admin(current_user)
    repo = SQLUserRepository(db)
    user = await repo.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    allowed = {"role", "display_name", "is_active", "totp_enabled", "email"}
    for key in body:
        if key not in allowed:
            raise HTTPException(status_code=400, detail=f"Cannot update field: {key}")

    if "role" in body:
        user.role = body["role"]
    if "display_name" in body:
        user.display_name = body["display_name"]
    if "is_active" in body:
        user.is_active = body["is_active"]
    if "totp_enabled" in body:
        user.totp_enabled = body["totp_enabled"]
    if "email" in body:
        user.email = body["email"]

    await repo.update(user)
    return {
        "id": str(user.id),
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role,
        "is_active": user.is_active,
        "totp_enabled": user.totp_enabled,
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


@router.delete("/users/{user_id}", status_code=204)
async def delete_user(
    user_id: uuid.UUID,
    db: DBSession,
    current_user: CurrentUser,
) -> None:
    """Hard-delete a user."""
    _require_admin(current_user)
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    stmt = delete(UserModel).where(UserModel.id == user_id)
    result = await db.execute(stmt)
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="User not found")


# =============================================================================
# Applications (all tenants)
# =============================================================================


@router.get("/applications")
async def list_all_applications(
    db: DBSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
) -> dict:
    """List all applications across all tenants."""
    _require_admin(current_user)
    offset, limit = _paginate(page, page_size)

    count_stmt = select(func.count(TenantApplicationModel.id))
    if status:
        count_stmt = count_stmt.where(TenantApplicationModel.status == status)
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = select(TenantApplicationModel).order_by(
        TenantApplicationModel.created_at.desc()
    )
    if status:
        stmt = stmt.where(TenantApplicationModel.status == status)
    stmt = stmt.offset(offset).limit(limit)
    result = await db.execute(stmt)
    rows = result.scalars().all()

    return {
        "data": [
            {
                "id": str(a.id),
                "owner_id": str(a.owner_id),
                "name": a.name,
                "status": a.status,
                "webhook_url": a.webhook_url,
                "liveness_threshold": a.liveness_threshold,
                "similarity_threshold": a.similarity_threshold,
                "allowed_ips": a.allowed_ips or [],
                "created_at": a.created_at.isoformat() if a.created_at else None,
                "updated_at": a.updated_at.isoformat() if a.updated_at else None,
            }
            for a in rows
        ],
        "pagination": {"page": page, "page_size": page_size, "total": total},
    }


@router.get("/applications/{app_id}")
async def get_application(
    app_id: uuid.UUID,
    db: DBSession,
    current_user: CurrentUser,
) -> dict:
    """Get application details (admin view — any tenant)."""
    _require_admin(current_user)
    repo = SQLTenantApplicationRepository(db)
    app = await repo.get_by_id(app_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    return {
        "id": str(app.id),
        "owner_id": str(app.owner_id),
        "name": app.name,
        "status": app.status,
        "webhook_url": app.webhook_url,
        "liveness_threshold": app.liveness_threshold,
        "similarity_threshold": getattr(app, "similarity_threshold", 0.75),
        "allowed_ips": app.allowed_ips or [],
        "created_at": app.created_at.isoformat() if app.created_at else None,
        "updated_at": app.updated_at.isoformat() if app.updated_at else None,
    }


@router.patch("/applications/{app_id}")
async def update_application(
    app_id: uuid.UUID,
    db: DBSession,
    current_user: CurrentUser,
    body: dict[str, Any] = {},
) -> dict:
    """Update any application (admin override — no owner check)."""
    _require_admin(current_user)
    repo = SQLTenantApplicationRepository(db)
    app = await repo.get_by_id(app_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    if "name" in body:
        app.name = body["name"]
    if "status" in body:
        app.status = body["status"]
    if "webhook_url" in body:
        app.webhook_url = body["webhook_url"]
    if "liveness_threshold" in body:
        app.liveness_threshold = body["liveness_threshold"]
    if "similarity_threshold" in body:
        app.similarity_threshold = body["similarity_threshold"]
    if "allowed_ips" in body:
        app.allowed_ips = body["allowed_ips"]

    app.updated_at = datetime.datetime.now(datetime.timezone.utc)
    await repo.update(app)
    return {
        "id": str(app.id),
        "name": app.name,
        "status": app.status,
        "updated_at": app.updated_at.isoformat(),
    }


@router.delete("/applications/{app_id}", status_code=204)
async def delete_application(
    app_id: uuid.UUID,
    db: DBSession,
    current_user: CurrentUser,
) -> None:
    """Hard-delete an application and all related data."""
    _require_admin(current_user)
    repo = SQLTenantApplicationRepository(db)
    app = await repo.get_by_id(app_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    # Cascade: delete face profiles, sessions, api keys, webhook deliveries
    await db.execute(delete(FaceProfileModel).where(FaceProfileModel.app_id == app_id))
    await db.execute(delete(AuthSessionModel).where(AuthSessionModel.app_id == app_id))
    await db.execute(delete(ApiKeyModel).where(ApiKeyModel.app_id == app_id))
    stmt = delete(TenantApplicationModel).where(TenantApplicationModel.id == app_id)
    await db.execute(stmt)


# =============================================================================
# API Keys (global view)
# =============================================================================


@router.get("/api-keys")
async def list_all_api_keys(
    db: DBSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
) -> dict:
    """List all API keys across all applications."""
    _require_admin(current_user)
    offset, limit = _paginate(page, page_size)

    count_stmt = select(func.count(ApiKeyModel.id))
    if status:
        count_stmt = count_stmt.where(ApiKeyModel.status == status)
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = select(ApiKeyModel).order_by(ApiKeyModel.created_at.desc())
    if status:
        stmt = stmt.where(ApiKeyModel.status == status)
    stmt = stmt.offset(offset).limit(limit)
    result = await db.execute(stmt)
    rows = result.scalars().all()

    return {
        "data": [
            {
                "id": str(k.id),
                "app_id": str(k.app_id),
                "key_prefix": k.key_prefix,
                "label": k.label,
                "status": k.status,
                "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
                "expires_at": k.expires_at.isoformat() if k.expires_at else None,
                "created_at": k.created_at.isoformat() if k.created_at else None,
                "revoked_at": k.revoked_at.isoformat() if k.revoked_at else None,
            }
            for k in rows
        ],
        "pagination": {"page": page, "page_size": page_size, "total": total},
    }


@router.post("/api-keys/{key_id}/revoke", status_code=204)
async def admin_revoke_api_key(
    key_id: uuid.UUID,
    db: DBSession,
    current_user: CurrentUser,
) -> None:
    """Revoke any API key (admin override)."""
    _require_admin(current_user)
    repo = SQLApiKeyRepository(db)
    key = await repo.get_by_id(key_id)
    if not key:
        raise HTTPException(status_code=404, detail="API key not found")
    await repo.revoke(key_id)


@router.delete("/api-keys/{key_id}", status_code=204)
async def admin_delete_api_key(
    key_id: uuid.UUID,
    db: DBSession,
    current_user: CurrentUser,
) -> None:
    """Hard-delete any API key."""
    _require_admin(current_user)
    repo = SQLApiKeyRepository(db)
    key = await repo.get_by_id(key_id)
    if not key:
        raise HTTPException(status_code=404, detail="API key not found")
    await repo.delete(key_id)


# =============================================================================
# Face Profiles (global view)
# =============================================================================


@router.get("/face-profiles")
async def list_all_face_profiles(
    db: DBSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    app_id: uuid.UUID | None = Query(None),
) -> dict:
    """List all face profiles with pagination. Optionally filter by app_id."""
    _require_admin(current_user)
    offset, limit = _paginate(page, page_size)

    count_stmt = select(func.count(FaceProfileModel.id))
    if app_id:
        count_stmt = count_stmt.where(FaceProfileModel.app_id == app_id)
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = select(FaceProfileModel).order_by(FaceProfileModel.created_at.desc())
    if app_id:
        stmt = stmt.where(FaceProfileModel.app_id == app_id)
    stmt = stmt.offset(offset).limit(limit)
    result = await db.execute(stmt)
    rows = result.scalars().all()

    return {
        "data": [
            {
                "id": str(f.id),
                "app_id": str(f.app_id),
                "external_user_id": f.external_user_id,
                "model_version": f.model_version,
                "is_active": f.is_active,
                "created_at": f.created_at.isoformat() if f.created_at else None,
                "updated_at": f.updated_at.isoformat() if f.updated_at else None,
            }
            for f in rows
        ],
        "pagination": {"page": page, "page_size": page_size, "total": total},
    }


@router.delete("/face-profiles/{profile_id}", status_code=204)
async def admin_delete_face_profile(
    profile_id: uuid.UUID,
    db: DBSession,
    current_user: CurrentUser,
) -> None:
    """Hard-delete a face profile."""
    _require_admin(current_user)
    stmt = delete(FaceProfileModel).where(FaceProfileModel.id == profile_id)
    result = await db.execute(stmt)
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Face profile not found")


# =============================================================================
# Auth Sessions (global view)
# =============================================================================


@router.get("/sessions")
async def list_all_sessions(
    db: DBSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
    app_id: uuid.UUID | None = Query(None),
) -> dict:
    """List all auth sessions with pagination."""
    _require_admin(current_user)
    offset, limit = _paginate(page, page_size)

    count_stmt = select(func.count(AuthSessionModel.id))
    if status:
        count_stmt = count_stmt.where(AuthSessionModel.status == status)
    if app_id:
        count_stmt = count_stmt.where(AuthSessionModel.app_id == app_id)
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = select(AuthSessionModel).order_by(AuthSessionModel.created_at.desc())
    if status:
        stmt = stmt.where(AuthSessionModel.status == status)
    if app_id:
        stmt = stmt.where(AuthSessionModel.app_id == app_id)
    stmt = stmt.offset(offset).limit(limit)
    result = await db.execute(stmt)
    rows = result.scalars().all()

    return {
        "data": [
            {
                "id": str(s.id),
                "app_id": str(s.app_id),
                "session_type": s.session_type,
                "status": s.status,
                "external_user_id": s.external_user_id,
                "liveness_class": s.liveness_class,
                "liveness_confidence": s.liveness_confidence,
                "similarity_score": s.similarity_score,
                "inference_time_ms": s.inference_time_ms,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "completed_at": s.completed_at.isoformat() if s.completed_at else None,
            }
            for s in rows
        ],
        "pagination": {"page": page, "page_size": page_size, "total": total},
    }
