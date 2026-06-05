"""Face operations router — register, authenticate, replace, delete, session poll.

All endpoints from API_SPECIFICATION.md §4.5 and §4.6.
All use X-API-Key authentication (not JWT Bearer).
"""

from __future__ import annotations

import base64
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status

from spectre.config import Settings
from spectre.domain.exceptions.face_exceptions import (
    FaceAlreadyRegisteredError,
    FaceProfileNotFoundError,
    ImageQualityInsufficientError,
    LivenessCheckFailedError,
)
from spectre.interface.dependencies import (
    AuthenticatedApp,
    DBSession,
    check_rate_limit,
    get_settings,
)
from spectre.interface.schemas.face_schema import (
    FaceAuthenticateRequest,
    FaceBenchmarkRequest,
    FaceBenchmarkResponse,
    FaceRegisterRequest,
    FaceReplaceRequest,
    FaceSessionResponse,
    SessionDetailResponse,
)
from spectre.infrastructure.repositories.sql_repositories import (
    SQLAuthSessionRepository,
    SQLFaceProfileRepository,
)

router = APIRouter(
    prefix="/api/v1",
    tags=["Face Operations"],
    dependencies=[Depends(check_rate_limit)],
)


def _build_face_use_case(request: Request, db, app, use_case_class, settings: Settings):
    fas_registry = getattr(request.app.state, "fas_registry", None)

    if fas_registry is None or fas_registry.loaded_count == 0:
        raise HTTPException(
            status_code=503,
            detail={"error_code": "MODEL_UNAVAILABLE", "message": "No FAS models loaded."},
        )

    active_id = settings.active_fas_model
    if not fas_registry.is_valid_model_id(active_id):
        raise HTTPException(
            status_code=503,
            detail={
                "error_code": "MODEL_UNAVAILABLE",
                "message": f"Active FAS model '{active_id}' is not loaded.",
            },
        )

    from spectre.infrastructure.ml.fas_adapter import KerasFASAdapter
    from spectre.infrastructure.ml.image_preprocessor import ImagePreprocessor
    from spectre.infrastructure.security.aes_encryption import AESEncryption

    face_repo = SQLFaceProfileRepository(db)
    session_repo = SQLAuthSessionRepository(db)
    fas_adapter = KerasFASAdapter(fas_registry, settings)
    preprocessor = ImagePreprocessor(settings)
    encryption = AESEncryption(settings)

    insightface_reg = getattr(request.app.state, "insightface_registry", None)
    if insightface_reg is not None and insightface_reg.is_loaded:
        from spectre.infrastructure.ml.insightface_embedding_adapter import InsightFaceEmbeddingAdapter
        embed_adapter = InsightFaceEmbeddingAdapter(insightface_reg)
    else:
        from spectre.infrastructure.ml.embedding_adapter import KerasEmbeddingAdapter
        legacy_registry = getattr(request.app.state, "model_registry", None)
        if legacy_registry is None:
            raise HTTPException(
                status_code=503,
                detail={
                    "error_code": "EMBEDDING_UNAVAILABLE",
                    "message": "No embedding model available (InsightFace down and legacy ModelRegistry missing).",
                },
            )
        embed_adapter = KerasEmbeddingAdapter(legacy_registry)

    return use_case_class(
        face_repo=face_repo,
        session_repo=session_repo,
        fas_model=fas_adapter,
        embedding_model=embed_adapter,
        preprocessor=preprocessor,
        encryption=encryption,
    )


def _decode_image(image_b64: str) -> bytes:
    """Decode base64 image and validate size."""
    try:
        data = base64.b64decode(image_b64)
    except Exception:
        raise HTTPException(
            status_code=400,
            detail={"error_code": "VALIDATION_ERROR", "message": "Invalid base64 image data."},
        )
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail={"error_code": "IMAGE_TOO_LARGE", "message": "Decoded image exceeds 5MB limit."},
        )
    return data


@router.post("/faces/register", status_code=202, response_model=FaceSessionResponse)
async def register_face(
    request: Request,
    body: FaceRegisterRequest,
    db: DBSession,
    app: AuthenticatedApp,
    settings: Settings = Depends(get_settings),
) -> dict:
    """Submit a face image for liveness detection and enrollment.

    Returns a session ID that can be polled or received via webhook.
    """
    from spectre.application.face_use_cases import RegisterFace

    image_bytes = _decode_image(body.image)
    use_case = _build_face_use_case(request, db, app, RegisterFace, settings)

    request_id = getattr(request.state, "request_id", None)
    session, diagnostics = await use_case.execute(
        app_id=app.id,
        external_user_id=body.external_user_id,
        image_bytes=image_bytes,
        liveness_threshold=settings.liveness_threshold,
        metadata=body.metadata,
        detail_mode=body.detail_mode,
        request_id=request_id,
    )

    if diagnostics is not None:
        await _persist_diagnostics(db, session, diagnostics)

    _dispatch_webhook(request, app, session)

    return {
        "session_id": str(session.id),
        "status": session.status.lower(),
        "created_at": session.created_at or datetime.datetime.now(datetime.timezone.utc),
        "diagnostics": diagnostics.model_dump() if diagnostics else None,
    }


@router.post("/faces/authenticate", status_code=202, response_model=FaceSessionResponse)
async def authenticate_face(
    request: Request,
    body: FaceAuthenticateRequest,
    db: DBSession,
    app: AuthenticatedApp,
    settings: Settings = Depends(get_settings),
) -> dict:
    """Submit a face image for liveness + identity verification.

    Returns a session ID that can be polled or received via webhook.
    """
    from spectre.application.face_use_cases import AuthenticateFace

    image_bytes = _decode_image(body.image)
    use_case = _build_face_use_case(request, db, app, AuthenticateFace, settings)

    request_id = getattr(request.state, "request_id", None)
    session, diagnostics = await use_case.execute(
        app_id=app.id,
        external_user_id=body.external_user_id,
        image_bytes=image_bytes,
        liveness_threshold=settings.liveness_threshold,
        similarity_threshold=settings.similarity_threshold,
        metadata=body.metadata,
        detail_mode=body.detail_mode,
        request_id=request_id,
    )

    if diagnostics is not None:
        await _persist_diagnostics(db, session, diagnostics)

    _dispatch_webhook(request, app, session)

    return {
        "session_id": str(session.id),
        "status": session.status.lower(),
        "created_at": session.created_at or datetime.datetime.now(datetime.timezone.utc),
        "diagnostics": diagnostics.model_dump() if diagnostics else None,
    }


@router.put("/faces/{external_user_id}", status_code=202, response_model=FaceSessionResponse)
async def replace_face(
    request: Request,
    external_user_id: str,
    db: DBSession,
    app: AuthenticatedApp,
    settings: Settings = Depends(get_settings),
) -> dict:
    """Replace an existing face profile with a new biometric template."""
    from spectre.application.face_use_cases import ReplaceFace

    body = await request.json()
    image_b64 = body.get("image_base64") or body.get("image", "")
    detail_mode = bool(body.get("detail_mode", False))
    image_bytes = _decode_image(image_b64)

    use_case = _build_face_use_case(request, db, app, ReplaceFace, settings)

    request_id = getattr(request.state, "request_id", None)
    session, diagnostics = await use_case.execute(
        app_id=app.id,
        external_user_id=external_user_id,
        image_bytes=image_bytes,
        liveness_threshold=settings.liveness_threshold,
        detail_mode=detail_mode,
        request_id=request_id,
    )

    if diagnostics is not None:
        await _persist_diagnostics(db, session, diagnostics)

    _dispatch_webhook(request, app, session)

    return {
        "session_id": str(session.id),
        "status": session.status.lower(),
        "created_at": session.created_at or datetime.datetime.now(datetime.timezone.utc),
        "diagnostics": diagnostics.model_dump() if diagnostics else None,
    }



@router.get("/faces", status_code=200, response_model=dict)
async def list_faces(

    db: DBSession,
    app: AuthenticatedApp,
    offset: int = 0,
    limit: int = 100,
) -> dict:
    """List all registered face profiles."""
    from spectre.application.face_use_cases import ListFaces

    face_repo = SQLFaceProfileRepository(db)
    use_case = ListFaces(face_repo=face_repo)
    profiles = await use_case.execute(app_id=app.id, offset=offset, limit=limit)
    
    return {
        "count": len(profiles),
        "profiles": [
            {
                "external_user_id": p.external_user_id,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
            for p in profiles
        ],
    }


@router.delete("/faces", status_code=200)
async def purge_faces(
    db: DBSession,
    app: AuthenticatedApp,
) -> dict:
    """Purge all face profiles for the application."""
    from spectre.application.face_use_cases import PurgeAllFaces

    face_repo = SQLFaceProfileRepository(db)
    use_case = PurgeAllFaces(face_repo=face_repo)
    count = await use_case.execute(app_id=app.id)
    return {"purged_count": count, "message": "All faces purged successfully."}


@router.delete("/faces/{external_user_id}", status_code=204)
async def delete_face(
    external_user_id: str,
    db: DBSession,
    app: AuthenticatedApp,
) -> None:
    """Delete a face profile."""
    from spectre.application.face_use_cases import DeleteFace

    face_repo = SQLFaceProfileRepository(db)
    use_case = DeleteFace(face_repo=face_repo)
    await use_case.execute(app_id=app.id, external_user_id=external_user_id)
    return None


@router.get("/faces/{external_user_id}/exists", status_code=200, response_model=dict)
async def check_face_exists(
    external_user_id: str,
    db: DBSession,
    app: AuthenticatedApp,
) -> dict:
    """Deterministic existence check for a face profile.

    Returns {"exists": true|false} based on the unique (app_id, external_user_id)
    index. Callers (e.g. the scanner frontend) use this to decide whether to
    call /faces/register or /faces/authenticate, removing the need for any
    retry-on-error mode flipping.
    """
    face_repo = SQLFaceProfileRepository(db)
    exists = await face_repo.exists(app.id, external_user_id)
    return {"exists": exists, "external_user_id": external_user_id}


@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
async def get_session(
    session_id: uuid.UUID,
    db: DBSession,
    app: AuthenticatedApp,
) -> dict:
    """Poll session status (fallback when webhook fails)."""
    session_repo = SQLAuthSessionRepository(db)
    session = await session_repo.get_by_id(session_id)

    if not session or session.app_id != app.id:
        raise HTTPException(status_code=404, detail="Session not found.")

    meta = session.client_metadata or {}
    diagnostics = meta.get("diagnostics") if isinstance(meta, dict) else None

    return {
        "session_id": str(session.id),
        "session_type": session.session_type,
        "status": session.status.lower(),
        "external_user_id": session.external_user_id,
        "liveness_class": session.liveness_class,
        "liveness_confidence": session.liveness_confidence,
        "similarity_score": session.similarity_score,
        "inference_time_ms": session.inference_time_ms,
        "created_at": session.created_at or datetime.datetime.now(datetime.timezone.utc),
        "completed_at": session.completed_at,
        "diagnostics": diagnostics,
    }


async def _persist_diagnostics(db, session, diagnostics) -> None:
    session_repo = SQLAuthSessionRepository(db)
    if session.client_metadata is None:
        session.client_metadata = {}
    session.client_metadata["diagnostics"] = diagnostics.model_dump()
    try:
        await session_repo.update(session)
    except Exception:
        pass


@router.post("/faces/benchmark", status_code=200, response_model=FaceBenchmarkResponse)
async def benchmark_face(
    request: Request,
    body: FaceBenchmarkRequest,
    app: AuthenticatedApp,
    settings: Settings = Depends(get_settings),
) -> dict:
    """Run all enabled benchmark FAS models on the same image and return side-by-side comparison."""
    from spectre.application.benchmark_use_cases import BenchmarkDisabledError, RunBenchmark
    from spectre.infrastructure.ml.image_preprocessor import ImagePreprocessor

    fas_registry = getattr(request.app.state, "fas_registry", None)

    if fas_registry is None:
        raise HTTPException(
            status_code=503,
            detail={"error_code": "MODEL_UNAVAILABLE", "message": "FAS registry not loaded."},
        )

    if not settings.benchmark_enabled:
        raise HTTPException(
            status_code=403,
            detail={
                "error_code": "BENCHMARK_DISABLED",
                "message": "Benchmark mode is not enabled. Admin must enable benchmark_enabled in config.",
            },
        )

    image_bytes = _decode_image(body.image)
    preprocessor = ImagePreprocessor(settings)
    use_case = RunBenchmark(fas_registry, settings, preprocessor)

    request_id = getattr(request.state, "request_id", None)

    try:
        report = use_case.execute(
            app_id=app.id,
            image_bytes=image_bytes,
            external_user_id=body.external_user_id,
            request_id=request_id,
        )
    except BenchmarkDisabledError as exc:
        raise HTTPException(
            status_code=403,
            detail={"error_code": "BENCHMARK_DISABLED", "message": str(exc)},
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error_code": "VALIDATION_ERROR", "message": str(exc)},
        )

    return report


def _dispatch_webhook(request: Request, app, session) -> None:
    """Fire-and-forget webhook dispatch via Celery."""
    if not app.has_webhook:
        return

    try:
        from spectre.workers.tasks.webhook_task import deliver_webhook

        deliver_webhook.delay(
            str(session.id),
            str(app.id),
        )
    except Exception:
        pass  # Webhook dispatch failure is non-fatal
