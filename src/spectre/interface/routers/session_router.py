"""Session listing router — dashboard endpoint for session history.

GET /api/v1/sessions from API_SPECIFICATION.md §4.6.
Requires JWT Bearer authentication.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query

from spectre.interface.dependencies import CurrentUser, DBSession
from spectre.infrastructure.repositories.sql_repositories import (
    SQLAuthSessionRepository,
    SQLTenantApplicationRepository,
)

router = APIRouter(prefix="/api/v1", tags=["Sessions"])


@router.get("/sessions", response_model=dict)
async def list_sessions(
    db: DBSession,
    current_user: CurrentUser,
    app_id: uuid.UUID = Query(..., description="Application ID to scope sessions"),
    status: str | None = Query(None, description="Filter by session status (PENDING, SUCCESS, FAILED)"),
    session_type: str | None = Query(None, description="registration | authentication"),
    external_user_id: str | None = Query(None, description="Filter by external user ID"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
) -> dict:
    """List authentication and registration sessions for the dashboard.

    Allows filtering by status, type, and user ID. Requires JWT authentication.
    """

    # Verify ownership
    app_repo = SQLTenantApplicationRepository(db)
    app = await app_repo.get_by_id(app_id)
    if not app or app.owner_id != current_user.id:
        from spectre.domain.exceptions.tenant_exceptions import ApplicationNotFoundError
        raise ApplicationNotFoundError()

    session_repo = SQLAuthSessionRepository(db)
    offset = (page - 1) * page_size
    sessions = await session_repo.list_by_app(
        app_id, offset=offset, limit=page_size, status=status
    )

    # Apply client-side filters for session_type and external_user_id
    if session_type:
        sessions = [s for s in sessions if s.session_type == session_type]
    if external_user_id:
        sessions = [s for s in sessions if s.external_user_id == external_user_id]

    return {
        "data": [
            {
                "session_id": str(s.id),
                "app_id": str(s.app_id),
                "session_type": s.session_type,
                "status": s.status.lower(),
                "external_user_id": s.external_user_id,
                "liveness_class": s.liveness_class,
                "liveness_confidence": s.liveness_confidence,
                "similarity_score": s.similarity_score,
                "inference_time_ms": s.inference_time_ms,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "completed_at": s.completed_at.isoformat() if s.completed_at else None,
            }
            for s in sessions
        ],
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": len(sessions),
        },
    }
