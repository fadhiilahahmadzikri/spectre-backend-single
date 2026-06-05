"""Authentication router — register, login, verify, TOTP, OAuth.

All endpoints from API_SPECIFICATION.md §4.1, §4.2, and §4.3.
"""

from __future__ import annotations

import datetime
import hashlib
import secrets
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status

from spectre.config import Settings, get_settings
from spectre.domain.entities.refresh_token import RefreshToken
from spectre.domain.exceptions.auth_exceptions import (
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    InvalidTOTPError,
)
from spectre.infrastructure.repositories.sql_repositories import (
    SQLRefreshTokenRepository,
    SQLUserRepository,
)
from spectre.infrastructure.security.jwt_handler import JWTHandler
from spectre.infrastructure.security.password_handler import PasswordHandler
from spectre.infrastructure.security.totp_handler import TOTPHandler
from spectre.interface.dependencies import CurrentUser, DBSession
from spectre.interface.schemas.auth_schema import (
    LoginRequest,
    RegisterRequest,
    TOTPConfirmRequest,
    TOTPVerifyRequest,
)
from spectre.infrastructure.security.aes_encryption import AESEncryption

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])


@router.post("/register", status_code=201)
async def register(
    request: Request,
    body: RegisterRequest,
    db: DBSession,
    settings: Settings = Depends(get_settings),
) -> dict:
    """Register a new tenant account."""
    user_repo = SQLUserRepository(db)
    pw_handler = PasswordHandler(settings)

    existing = await user_repo.get_by_email(body.email.lower())
    if existing:
        raise EmailAlreadyRegisteredError()

    from spectre.domain.entities.user import User, UserIdentity

    user = await user_repo.create(
        User(
            id=uuid.uuid4(),
            email=body.email.lower(),
            display_name=body.display_name,
            is_active=True,
        )
    )

    await user_repo.create_identity(
        UserIdentity(
            id=uuid.uuid4(),
            user_id=user.id,
            provider="local",
            provider_user_id=body.email.lower(),
            password_hash=pw_handler.hash(body.password),
        )
    )

    return {
        "user_id": str(user.id),
        "email": user.email,
        "status": "active",
        "message": "Registration successful.",
    }


@router.post("/login")
async def login(
    request: Request,
    body: LoginRequest,
    db: DBSession,
    settings: Settings = Depends(get_settings),
) -> dict:
    """Authenticate with email and password."""
    user_repo = SQLUserRepository(db)
    pw_handler = PasswordHandler(settings)
    jwt_handler = JWTHandler(settings)

    user = await user_repo.get_by_email(body.email.lower())
    if not user:
        raise InvalidCredentialsError()

    identity = await user_repo.get_identity("local", body.email.lower())
    if not identity or not identity.password_hash:
        raise InvalidCredentialsError()

    if not pw_handler.verify(body.password, identity.password_hash):
        raise InvalidCredentialsError()

    if not user.is_active:
        from spectre.domain.exceptions.auth_exceptions import AccountDisabledError
        raise AccountDisabledError()

    if user.requires_totp:
        # Return partial auth — requires TOTP step
        challenge = jwt_handler.create_access_token(
            user.id, extra_claims={"type": "totp_challenge"}
        )
        return {
            "totp_required": True,
            "totp_challenge_token": challenge,
            "expires_in": 300,
        }

    # Full auth
    access_token = jwt_handler.create_access_token(
        user.id, extra_claims={"role": user.role}
    )
    refresh_raw = secrets.token_urlsafe(48)
    refresh_hash = hashlib.sha256(refresh_raw.encode()).hexdigest()

    refresh_repo = SQLRefreshTokenRepository(db)
    await refresh_repo.create(
        RefreshToken(
            id=uuid.uuid4(),
            user_id=user.id,
            token_hash=refresh_hash,
            expires_at=datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(days=settings.jwt_refresh_token_expire_days),
        )
    )

    return {
        "access_token": access_token,
        "refresh_token": refresh_raw,
        "token_type": "Bearer",
        "expires_in": settings.jwt_access_token_expire_minutes * 60,
        "user_id": str(user.id),
        "display_name": user.display_name,
        "totp_required": False,
    }


@router.post("/refresh")
async def refresh_token(
    request: Request,
    db: DBSession,
    settings: Settings = Depends(get_settings),
) -> dict:
    """Rotate refresh token — returns new access + refresh tokens."""
    body = await request.json()
    raw_token = body.get("refresh_token")
    if not raw_token:
        raise InvalidRefreshTokenError()

    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    jwt_handler = JWTHandler(settings)
    refresh_repo = SQLRefreshTokenRepository(db)

    stored = await refresh_repo.get_by_hash(token_hash)
    if not stored or not stored.is_valid:
        raise InvalidRefreshTokenError()

    # Revoke old token
    await refresh_repo.revoke(stored.id)

    # Issue new pair
    user_repo = SQLUserRepository(db)
    
    access_token = jwt_handler.create_access_token(stored.user_id)
    new_raw = secrets.token_urlsafe(48)
    new_hash = hashlib.sha256(new_raw.encode()).hexdigest()

    await refresh_repo.create(
        RefreshToken(
            id=uuid.uuid4(),
            user_id=stored.user_id,
            token_hash=new_hash,
            expires_at=datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(days=settings.jwt_refresh_token_expire_days),
        )
    )

    return {
        "access_token": access_token,
        "refresh_token": new_raw,
        "token_type": "Bearer",
        "expires_in": settings.jwt_access_token_expire_minutes * 60,
    }


@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    db: DBSession,
    current_user: CurrentUser,
) -> None:
    """Revoke the current refresh token."""
    body = await request.json()
    raw_token = body.get("refresh_token")
    if raw_token:
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        refresh_repo = SQLRefreshTokenRepository(db)
        stored = await refresh_repo.get_by_hash(token_hash)
        if stored:
            await refresh_repo.revoke(stored.id)
    return None


@router.post("/totp/setup")
async def totp_setup(
    request: Request,
    db: DBSession,
    current_user: CurrentUser,
    settings: Settings = Depends(get_settings),
) -> dict:
    """Setup TOTP (2FA) for the authenticated user."""
    totp_handler = TOTPHandler(settings)
    encryption = AESEncryption(settings)

    secret = totp_handler.generate_secret()
    uri = totp_handler.get_provisioning_uri(secret, current_user.email)

    # Encrypt and store (not enabled until confirmed)
    user_repo = SQLUserRepository(db)
    current_user.totp_secret_encrypted = encryption.encrypt_string(secret)
    current_user.updated_at = datetime.datetime.now(datetime.timezone.utc)
    await user_repo.update(current_user)

    return {"secret": secret, "provisioning_uri": uri}


@router.post("/totp/confirm")
async def totp_confirm(
    request: Request,
    body: TOTPConfirmRequest,
    db: DBSession,
    current_user: CurrentUser,
    settings: Settings = Depends(get_settings),
) -> dict:
    """Confirm TOTP setup with a valid code."""
    totp_handler = TOTPHandler(settings)
    encryption = AESEncryption(settings)

    if not current_user.totp_secret_encrypted:
        raise InvalidTOTPError("TOTP not set up. Call /totp/setup first.")

    secret = encryption.decrypt_string(current_user.totp_secret_encrypted)
    if not totp_handler.verify(secret, body.code):
        raise InvalidTOTPError()

    user_repo = SQLUserRepository(db)
    current_user.totp_enabled = True
    current_user.updated_at = datetime.datetime.now(datetime.timezone.utc)
    await user_repo.update(current_user)

    return {"message": "TOTP enabled successfully."}


@router.post("/totp/verify")
async def totp_verify(
    request: Request,
    body: TOTPVerifyRequest,
    db: DBSession,
    settings: Settings = Depends(get_settings),
) -> dict:
    """Verify TOTP during login flow."""
    # Extract user_id from challenge token
    jwt_handler = JWTHandler(settings)
    challenge_token = getattr(body, "totp_challenge_token", None)

    # Body may contain the challenge token
    raw_body = await request.json()
    challenge = raw_body.get("totp_challenge_token", "")

    payload = jwt_handler.decode_token(challenge)
    if payload.get("type") != "totp_challenge":
        from spectre.domain.exceptions.auth_exceptions import InvalidTokenError
        raise InvalidTokenError("Invalid challenge token.")

    user_id = uuid.UUID(payload["sub"])
    user_repo = SQLUserRepository(db)
    user = await user_repo.get_by_id(user_id)

    if not user or not user.totp_secret_encrypted:
        raise InvalidCredentialsError("TOTP not configured.")

    encryption = AESEncryption(settings)
    totp_handler = TOTPHandler(settings)

    secret = encryption.decrypt_string(user.totp_secret_encrypted)
    if not totp_handler.verify(secret, body.code):
        raise InvalidTOTPError()

    # Issue full tokens
    access_token = jwt_handler.create_access_token(user.id)
    refresh_raw = secrets.token_urlsafe(48)
    refresh_hash = hashlib.sha256(refresh_raw.encode()).hexdigest()

    refresh_repo = SQLRefreshTokenRepository(db)
    await refresh_repo.create(
        RefreshToken(
            id=uuid.uuid4(),
            user_id=user.id,
            token_hash=refresh_hash,
            expires_at=datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(days=settings.jwt_refresh_token_expire_days),
        )
    )

    return {
        "access_token": access_token,
        "refresh_token": refresh_raw,
        "token_type": "Bearer",
        "expires_in": settings.jwt_access_token_expire_minutes * 60,
    }


# =============================================================================
# Google OAuth
# =============================================================================

@router.get("/oauth/google")
async def google_login(request: Request, settings: Settings = Depends(get_settings)):
    """Initiate Google OAuth flow."""
    from spectre.infrastructure.security.oauth_client import oauth
    
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(status_code=400, detail="Google OAuth is not configured on this server")
        
    redirect_uri = settings.google_redirect_uri
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/oauth/google/callback")
async def google_callback(
    request: Request, 
    db: DBSession,
    settings: Settings = Depends(get_settings)
) -> dict:
    """Handle Google OAuth callback."""
    from spectre.infrastructure.security.oauth_client import oauth
    
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(status_code=400, detail="Google OAuth is not configured on this server")
    from spectre.application.oauth_use_cases import GoogleOAuthUseCase
    from spectre.infrastructure.repositories.sql_repositories import (
        SQLUserRepository,
        SQLRefreshTokenRepository,
    )
    from fastapi import HTTPException

    try:
        token = await oauth.google.authorize_access_token(request)
    except Exception as e:
        if "mismatching_state" in str(e).lower():
            raise HTTPException(
                status_code=400,
                detail={"error_code": "OAUTH_STATE_MISMATCH", "message": "OAuth session expired or already used. Please try again."},
            )
        raise HTTPException(status_code=400, detail={"error_code": "OAUTH_FAILED", "message": str(e)})
    user_info = token.get("userinfo")
    
    if not user_info:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Failed to retrieve user info from Google.")

    user_repo = SQLUserRepository(db)
    use_case = GoogleOAuthUseCase(user_repo)
    user, created = await use_case.execute(user_info)

    # Issue tokens
    jwt_handler = JWTHandler(settings)
    access_token = jwt_handler.create_access_token(
        user.id, extra_claims={"role": user.role}
    )

    refresh_raw = secrets.token_urlsafe(48)
    refresh_hash = hashlib.sha256(refresh_raw.encode()).hexdigest()

    refresh_repo = SQLRefreshTokenRepository(db)
    await refresh_repo.create(
        RefreshToken(
            id=uuid.uuid4(),
            user_id=user.id,
            token_hash=refresh_hash,
            expires_at=datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(days=settings.jwt_refresh_token_expire_days),
        )
    )

    from urllib.parse import urlencode
    from fastapi.responses import RedirectResponse

    # Redirect to frontend with tokens
    frontend_url = getattr(settings, "oauth_frontend_redirect", None) or "http://localhost:5173"

    params_dict = {
        "access_token": access_token,
        "refresh_token": refresh_raw,
        "user_id": str(user.id),
        "email": user.email,
        "display_name": user.display_name or "",
        "role": user.role,
    }
    params = urlencode(params_dict)
    return RedirectResponse(url=f"{frontend_url}/oauth/callback?{params}")
