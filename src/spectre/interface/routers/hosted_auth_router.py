from __future__ import annotations

import datetime
import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status

from spectre.application.face_use_cases import AuthenticateFace, RegisterFace
from spectre.config import Settings
from spectre.domain.entities.auth_session import AuthSession
from spectre.domain.exceptions.face_exceptions import (
    FaceAlreadyRegisteredError,
    FaceMatchFailedError,
    FaceProfileNotFoundError,
    ImageQualityInsufficientError,
    LivenessCheckFailedError,
)
from spectre.infrastructure.repositories.sql_repositories import (
    SQLAuditLogRepository,
    SQLAuthSessionRepository,
    SQLFaceProfileRepository,
    SQLWebhookRepository,
)
from spectre.infrastructure.security.aes_encryption import AESEncryption
from spectre.infrastructure.security.hosted_auth import (
    append_query_params,
    build_hosted_auth_url,
    create_client_secret,
    create_exchange_code,
    hash_token,
    request_fingerprint,
    utcnow,
    validate_redirect_url,
    verify_token_hash,
)
from spectre.infrastructure.security.hosted_jwks import build_jwks, sign_hosted_result_token
from spectre.infrastructure.security.webhook_signature import sign_webhook_payload
from spectre.interface.dependencies import DBSession, SecretApp, get_settings
from spectre.interface.routers.face_router import _build_face_use_case, _decode_image
from spectre.interface.schemas.hosted_auth_schema import (
    HostedAuthBootstrapResponse,
    HostedAuthCaptureRequest,
    HostedAuthCaptureResponse,
    HostedAuthExchangeRequest,
    HostedAuthExchangeResponse,
    HostedAuthSessionCreateRequest,
    HostedAuthSessionCreateResponse,
    HostedAuthSessionResponse,
)

router = APIRouter(tags=["Hosted Auth"])


@router.post(
    "/api/v1/hosted/auth-sessions",
    status_code=201,
    response_model=HostedAuthSessionCreateResponse,
)
async def create_hosted_auth_session(
    request: Request,
    body: HostedAuthSessionCreateRequest,
    db: DBSession,
    secret_app: SecretApp,
    settings: Settings = Depends(get_settings),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    if idempotency_key and len(idempotency_key) > 64:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": "INVALID_IDEMPOTENCY_KEY",
                "message": "Idempotency-Key must be 64 characters or fewer.",
            },
        )

    app = secret_app.app
    return_url = validate_redirect_url(body.return_url, app)
    cancel_url = validate_redirect_url(body.cancel_url, app)
    fingerprint = request_fingerprint(body.model_dump(mode="json"))
    session_repo = SQLAuthSessionRepository(db)

    if idempotency_key:
        existing = await session_repo.get_by_idempotency_key(app.id, idempotency_key)
        if existing is not None:
            metadata = existing.client_metadata or {}
            if metadata.get("request_fingerprint") != fingerprint:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "error_code": "IDEMPOTENCY_CONFLICT",
                        "message": "Idempotency-Key was already used with different parameters.",
                    },
                )
            client_secret = create_client_secret(
                app_id=app.id, idempotency_key=idempotency_key, settings=settings
            )
            return _creation_response(existing, client_secret, settings)

    client_secret = create_client_secret(
        app_id=app.id, idempotency_key=idempotency_key, settings=settings
    )
    now = utcnow()
    expires_at = now + datetime.timedelta(minutes=settings.hosted_session_ttl_minutes)
    session = AuthSession(
        id=uuid.uuid4(),
        app_id=app.id,
        session_type="hosted_auth",
        status="PROCESSING",
        lifecycle_state="CREATED",
        external_user_id=body.external_user_id,
        expires_at=expires_at,
        idempotency_key=idempotency_key,
        client_secret_hash=hash_token(client_secret, settings),
        return_url=return_url,
        cancel_url=cancel_url,
        client_metadata={
            "mode": body.mode,
            "request_fingerprint": fingerprint,
            "metadata": body.metadata or {},
        },
        created_at=now,
    )
    session = await session_repo.create(session)
    await _append_audit(
        db,
        "hosted_auth_session.created",
        app_id=app.id,
        api_key_id=secret_app.api_key.id,
        resource_id=str(session.id),
        request=request,
    )
    return _creation_response(session, client_secret, settings)


@router.get(
    "/api/v1/hosted/auth-sessions/{session_id}/bootstrap",
    response_model=HostedAuthBootstrapResponse,
)
async def bootstrap_hosted_auth_session(
    session_id: uuid.UUID,
    db: DBSession,
    settings: Settings = Depends(get_settings),
    client_secret: str = Query(...),
) -> dict[str, Any]:
    session = await _load_client_session(db, session_id, client_secret, settings)
    if _is_expired(session):
        await _expire_session(db, session)
    return {
        "id": str(session.id),
        "status": session.status.lower(),
        "lifecycle_state": session.lifecycle_state.lower(),
        "mode": _session_mode(session),
        "external_user_id": session.external_user_id,
        "expires_at": session.expires_at,
        "locked": session.is_locked,
        "return_url": session.return_url,
        "cancel_url": session.cancel_url,
        "ui": _hosted_ui_config(settings),
    }


@router.post(
    "/api/v1/hosted/auth-sessions/{session_id}/capture",
    response_model=HostedAuthCaptureResponse,
)
async def capture_hosted_auth_session(
    request: Request,
    session_id: uuid.UUID,
    body: HostedAuthCaptureRequest,
    db: DBSession,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    session = await _load_client_session(db, session_id, body.client_secret, settings)
    if _is_expired(session):
        await _expire_session(db, session)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error_code": "SESSION_EXPIRED", "message": "Hosted auth session expired."},
        )
    if session.is_terminal:
        return _capture_response(session, None)

    now = utcnow()
    if not session.is_locked:
        session.mark_locked(now)
        await SQLAuthSessionRepository(db).update(session)
        await _append_audit(
            db,
            "hosted_auth_session.locked",
            app_id=session.app_id,
            resource_id=str(session.id),
            request=request,
        )

    image_bytes = _decode_image(body.image)
    effective_mode = await _resolve_effective_mode(db, session)
    result_session: AuthSession | None = None
    reason_code: str | None = None

    try:
        use_case_class = RegisterFace if effective_mode == "register" else AuthenticateFace
        use_case = _build_face_use_case(request, db, session, use_case_class, settings)
        metadata = {
            "hosted_session_id": str(session.id),
            "hosted_mode": _session_mode(session),
            "effective_mode": effective_mode,
        }
        if effective_mode == "register":
            result_session, diagnostics = await use_case.execute(
                app_id=session.app_id,
                external_user_id=session.external_user_id or "",
                image_bytes=image_bytes,
                liveness_threshold=settings.liveness_threshold,
                metadata=metadata,
                detail_mode=body.detail_mode,
                request_id=getattr(request.state, "request_id", None),
            )
        else:
            result_session, diagnostics = await use_case.execute(
                app_id=session.app_id,
                external_user_id=session.external_user_id or "",
                image_bytes=image_bytes,
                liveness_threshold=settings.liveness_threshold,
                similarity_threshold=settings.similarity_threshold,
                metadata=metadata,
                detail_mode=body.detail_mode,
                request_id=getattr(request.state, "request_id", None),
            )
        _copy_face_result(session, result_session, diagnostics)
        session.mark_succeeded(utcnow())
    except (
        FaceAlreadyRegisteredError,
        FaceMatchFailedError,
        FaceProfileNotFoundError,
        ImageQualityInsufficientError,
        LivenessCheckFailedError,
    ) as exc:
        reason_code = _reason_code(exc)
        session.status = _status_for_exception(exc)
        session.mark_failed(utcnow(), reason_code)
    except Exception:
        reason_code = "capture_failed"
        session.status = "FAILED"
        session.mark_failed(utcnow(), reason_code)
    finally:
        if session.is_terminal and session.exchange_code_hash is None:
            exchange_code = create_exchange_code()
            session.exchange_code_hash = hash_token(exchange_code, settings)
            session.exchange_code_expires_at = utcnow() + datetime.timedelta(
                seconds=settings.hosted_exchange_code_ttl_seconds
            )
        else:
            exchange_code = None
        await SQLAuthSessionRepository(db).update(session)

    event_type = (
        "auth_session.succeeded"
        if session.lifecycle_state == "SUCCEEDED"
        else "auth_session.failed"
    )
    await _emit_session_event(db, settings, session, event_type)
    await _append_audit(
        db,
        f"hosted_auth_session.{session.lifecycle_state.lower()}",
        app_id=session.app_id,
        resource_id=str(session.id),
        metadata={"reason_code": session.failure_reason},
        request=request,
    )
    return _capture_response(session, exchange_code)


@router.post(
    "/api/v1/hosted/auth-sessions/{session_id}/exchange",
    response_model=HostedAuthExchangeResponse,
)
async def exchange_hosted_auth_session(
    request: Request,
    session_id: uuid.UUID,
    body: HostedAuthExchangeRequest,
    db: DBSession,
    secret_app: SecretApp,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    session_repo = SQLAuthSessionRepository(db)
    session = await session_repo.get_by_id(session_id)
    if not session or session.app_id != secret_app.app.id:
        raise HTTPException(status_code=404, detail="Hosted auth session not found.")
    if not verify_token_hash(body.code, session.exchange_code_hash, settings):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error_code": "INVALID_EXCHANGE_CODE", "message": "Exchange code is invalid."},
        )
    if session.exchanged_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error_code": "EXCHANGE_CODE_USED", "message": "Exchange code was already used."},
        )
    if not session.exchange_code_expires_at or _as_utc(session.exchange_code_expires_at) < utcnow():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error_code": "EXCHANGE_CODE_EXPIRED", "message": "Exchange code expired."},
        )

    session.exchanged_at = utcnow()
    await session_repo.update(session)
    await _append_audit(
        db,
        "hosted_auth_session.exchanged",
        app_id=session.app_id,
        api_key_id=secret_app.api_key.id,
        resource_id=str(session.id),
        request=request,
    )
    response = _session_response(session)
    response["result_token"] = sign_hosted_result_token(
        settings=settings,
        session_id=session.id,
        app_id=session.app_id,
        external_user_id=session.external_user_id,
        status=session.status.lower(),
    )
    return response


@router.get(
    "/api/v1/hosted/auth-sessions/{session_id}",
    response_model=HostedAuthSessionResponse,
)
async def get_hosted_auth_session(
    session_id: uuid.UUID,
    db: DBSession,
    secret_app: SecretApp,
) -> dict[str, Any]:
    session = await SQLAuthSessionRepository(db).get_by_id(session_id)
    if not session or session.app_id != secret_app.app.id:
        raise HTTPException(status_code=404, detail="Hosted auth session not found.")
    return _session_response(session)


@router.get("/.well-known/jwks.json", response_model=dict)
async def hosted_jwks(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    return build_jwks(settings)


async def _load_client_session(
    db: Any, session_id: uuid.UUID, client_secret: str, settings: Settings
) -> AuthSession:
    session = await SQLAuthSessionRepository(db).get_by_id(session_id)
    if not session or session.session_type != "hosted_auth":
        raise HTTPException(status_code=404, detail="Hosted auth session not found.")
    if not verify_token_hash(client_secret, session.client_secret_hash, settings):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error_code": "INVALID_CLIENT_SECRET", "message": "Client secret is invalid."},
        )
    return session


def _is_expired(session: AuthSession) -> bool:
    return bool(session.expires_at and _as_utc(session.expires_at) < utcnow())


def _as_utc(value: datetime.datetime) -> datetime.datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=datetime.timezone.utc)
    return value.astimezone(datetime.timezone.utc)


async def _expire_session(db: Any, session: AuthSession) -> None:
    if session.is_terminal:
        return
    session.lifecycle_state = "EXPIRED"
    session.status = "FAILED"
    session.failure_reason = "session_expired"
    session.completed_at = utcnow()
    await SQLAuthSessionRepository(db).update(session)


def _session_mode(session: AuthSession) -> str:
    metadata = session.client_metadata or {}
    mode = metadata.get("mode")
    return mode if mode in ("register", "authenticate", "auto") else "authenticate"


async def _resolve_effective_mode(db: Any, session: AuthSession) -> str:
    mode = _session_mode(session)
    if mode != "auto":
        return mode
    exists = await SQLFaceProfileRepository(db).exists(
        session.app_id,
        session.external_user_id or "",
    )
    return "authenticate" if exists else "register"


def _copy_face_result(
    session: AuthSession,
    result_session: AuthSession,
    diagnostics: Any | None,
) -> None:
    session.status = result_session.status
    session.liveness_class = result_session.liveness_class
    session.liveness_confidence = result_session.liveness_confidence
    session.similarity_score = result_session.similarity_score
    session.inference_time_ms = result_session.inference_time_ms
    metadata = session.client_metadata or {}
    metadata["legacy_session_id"] = str(result_session.id)
    if diagnostics is not None:
        metadata["diagnostics"] = diagnostics.model_dump()
    session.client_metadata = metadata


def _status_for_exception(exc: Exception) -> str:
    if isinstance(exc, LivenessCheckFailedError):
        return "SPOOF_DETECTED"
    if isinstance(exc, FaceMatchFailedError):
        return "REJECTED"
    return "FAILED"


def _reason_code(exc: Exception) -> str:
    if isinstance(exc, FaceAlreadyRegisteredError):
        return "face_already_registered"
    if isinstance(exc, FaceMatchFailedError):
        return "face_mismatch"
    if isinstance(exc, FaceProfileNotFoundError):
        return "face_profile_not_found"
    if isinstance(exc, ImageQualityInsufficientError):
        return "image_quality_insufficient"
    if isinstance(exc, LivenessCheckFailedError):
        return "spoof_detected"
    return "capture_failed"


def _creation_response(
    session: AuthSession, client_secret: str, settings: Settings
) -> dict[str, Any]:
    return {
        "id": str(session.id),
        "status": session.lifecycle_state.lower(),
        "mode": _session_mode(session),
        "external_user_id": session.external_user_id,
        "client_secret": client_secret,
        "hosted_url": build_hosted_auth_url(
            base_url=settings.hosted_auth_base_url,
            session_id=session.id,
            client_secret=client_secret,
        ),
        "expires_at": session.expires_at,
    }


def _capture_response(
    session: AuthSession, exchange_code: str | None
) -> dict[str, Any]:
    redirect_url = None
    if exchange_code and session.return_url:
        redirect_url = append_query_params(
            session.return_url,
            {
                "spectre_session_id": str(session.id),
                "code": exchange_code,
                "status": session.status.lower(),
            },
        )
    return {
        "id": str(session.id),
        "status": session.status.lower(),
        "lifecycle_state": session.lifecycle_state.lower(),
        "exchange_code": exchange_code,
        "redirect_url": redirect_url,
        "reason_code": session.failure_reason,
    }


def _session_response(session: AuthSession) -> dict[str, Any]:
    return {
        "id": str(session.id),
        "app_id": str(session.app_id),
        "mode": _session_mode(session),
        "external_user_id": session.external_user_id,
        "status": session.status.lower(),
        "lifecycle_state": session.lifecycle_state.lower(),
        "reason_code": session.failure_reason,
        "created_at": session.created_at,
        "locked_at": session.locked_at,
        "completed_at": session.completed_at,
        "exchanged_at": session.exchanged_at,
    }


def _hosted_ui_config(settings: Settings) -> dict[str, Any]:
    return {
        "show_config_button": False,
        "allow_runtime_config": False,
        "require_pose": True,
        "show_preview": False,
        "detail_mode": settings.detail_mode_default,
        "benchmark_mode": settings.benchmark_enabled,
        "success_color": "#22c55e",
        "failure_color": "#ef4444",
    }


async def _emit_session_event(
    db: Any,
    settings: Settings,
    session: AuthSession,
    event_type: str,
) -> None:
    event_id = f"evt_{uuid.uuid4().hex}"
    payload = {
        "id": event_id,
        "type": event_type,
        "created": int(utcnow().timestamp()),
        "data": {"object": _safe_event_data(session)},
    }
    webhook_repo = SQLWebhookRepository(db)
    _, inserted = await webhook_repo.record_event(
        event_id=event_id,
        app_id=session.app_id,
        event_type=event_type,
        payload=payload,
    )
    if not inserted:
        return

    raw_body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    encryption = AESEncryption(settings)
    endpoints = await webhook_repo.list_active_endpoints_for_event(session.app_id, event_type)
    for endpoint in endpoints:
        secret = encryption.decrypt_string(endpoint.secret_encrypted)
        signature = sign_webhook_payload(raw_body, secret)
        await webhook_repo.create_delivery(
            delivery_id=uuid.uuid4(),
            event_id=event_id,
            endpoint_id=endpoint.id,
            signature_header=signature,
        )


def _safe_event_data(session: AuthSession) -> dict[str, Any]:
    return {
        "session_id": str(session.id),
        "app_id": str(session.app_id),
        "external_user_id": session.external_user_id,
        "mode": _session_mode(session),
        "status": session.status.lower(),
        "lifecycle_state": session.lifecycle_state.lower(),
        "reason_code": session.failure_reason,
        "created_at": session.created_at.isoformat() if session.created_at else None,
        "locked_at": session.locked_at.isoformat() if session.locked_at else None,
        "completed_at": session.completed_at.isoformat() if session.completed_at else None,
    }


async def _append_audit(
    db: Any,
    event_type: str,
    *,
    app_id: uuid.UUID | None,
    api_key_id: uuid.UUID | None = None,
    resource_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    request: Request | None = None,
) -> None:
    client_ip = request.client.host if request and request.client else None
    await SQLAuditLogRepository(db).append(
        event_type=event_type,
        app_id=app_id,
        api_key_id=api_key_id,
        resource_type="auth_session",
        resource_id=resource_id,
        metadata=metadata,
        ip_address=client_ip,
    )
