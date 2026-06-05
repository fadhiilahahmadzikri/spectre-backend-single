"""Authentication use cases — register, login, verify, TOTP, OAuth."""

from __future__ import annotations

import datetime
import secrets
import uuid
from typing import Any

from spectre.config import Settings
from spectre.core.logger import get_logger
from spectre.domain.entities.user import User
from spectre.domain.exceptions.auth_exceptions import (
    AccountDisabledError,
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    InvalidTOTPError,
    TOTPRequiredError,
)
from spectre.domain.ports.repositories import AbstractUserRepository
from spectre.infrastructure.security.aes_encryption import AESEncryption
from spectre.infrastructure.security.jwt_handler import JWTHandler
from spectre.infrastructure.security.password_handler import PasswordHandler
from spectre.infrastructure.security.totp_handler import TOTPHandler

logger = get_logger(__name__)


class RegisterUser:
    """Register a new tenant account holder."""

    def __init__(
        self,
        user_repo: AbstractUserRepository,
        password_handler: PasswordHandler,
        settings: Settings,
    ) -> None:
        self._user_repo = user_repo
        self._pw = password_handler
        self._settings = settings

    async def execute(
        self, email: str, password: str, display_name: str | None = None
    ) -> User:
        """Create a new user.

        Returns:
            The created User.
        """
        existing = await self._user_repo.get_by_email(email.lower())
        if existing:
            raise EmailAlreadyRegisteredError()

        user = User(
            id=uuid.uuid4(),
            email=email.lower(),
            display_name=display_name,
            is_active=True,
        )
        user = await self._user_repo.create(user)

        identity = UserIdentity(
            id=uuid.uuid4(),
            user_id=user.id,
            provider="local",
            provider_user_id=email.lower(),
            password_hash=self._pw.hash(password),
        )
        await self._user_repo.create_identity(identity)

        logger.info("user_registered", user_id=str(user.id), email=user.email)
        return user


class LoginUser:
    """Authenticate a user with email + password, returning tokens."""

    def __init__(
        self,
        user_repo: AbstractUserRepository,
        password_handler: PasswordHandler,
        jwt_handler: JWTHandler,
    ) -> None:
        self._user_repo = user_repo
        self._pw = password_handler
        self._jwt = jwt_handler

    async def execute(
        self, email: str, password: str
    ) -> dict[str, Any]:
        """Authenticate and return access/refresh tokens.

        Returns:
            Dict with access_token, refresh_token, user_id, requires_totp.

        Raises:
            InvalidCredentialsError, AccountDisabledError,
            TOTPRequiredError (if TOTP is enabled — token is partial).
        """
        user = await self._user_repo.get_by_email(email.lower())
        if not user:
            raise InvalidCredentialsError()

        identity = await self._user_repo.get_identity("local", email.lower())
        if not identity or not identity.password_hash:
            raise InvalidCredentialsError()

        if not self._pw.verify(password, identity.password_hash):
            raise InvalidCredentialsError()

        if not user.is_active:
            raise AccountDisabledError()

        if user.requires_totp:
            # Return partial token — requires TOTP step
            partial_token = self._jwt.create_access_token(
                user.id, extra_claims={"type": "totp_pending"}
            )
            raise TOTPRequiredError()

        access_token = self._jwt.create_access_token(
            user.id, extra_claims={"role": user.role}
        )
        refresh_token = secrets.token_urlsafe(48)

        logger.info("user_login", user_id=str(user.id))

        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user_id": str(user.id),
            "display_name": user.display_name,
            "role": user.role,
        }


class SetupTOTP:
    """Enable TOTP (2FA) for a user."""

    def __init__(
        self,
        user_repo: AbstractUserRepository,
        totp_handler: TOTPHandler,
        encryption: AESEncryption,
    ) -> None:
        self._user_repo = user_repo
        self._totp = totp_handler
        self._enc = encryption

    async def execute(self, user_id: uuid.UUID) -> dict[str, str]:
        """Generate TOTP secret and provisioning URI.

        Returns:
            Dict with secret (for backup) and provisioning_uri (for QR code).
        """
        user = await self._user_repo.get_by_id(user_id)
        if not user:
            raise InvalidCredentialsError("User not found.")

        secret = self._totp.generate_secret()
        uri = self._totp.get_provisioning_uri(secret, user.email)

        # Encrypt and store the secret (not enabled until confirmed)
        user.totp_secret_encrypted = self._enc.encrypt_string(secret)
        user.updated_at = datetime.datetime.now(datetime.timezone.utc)
        await self._user_repo.update(user)

        return {"secret": secret, "provisioning_uri": uri}


class ConfirmTOTP:
    """Confirm TOTP setup with a valid code, enabling 2FA."""

    def __init__(
        self,
        user_repo: AbstractUserRepository,
        totp_handler: TOTPHandler,
        encryption: AESEncryption,
    ) -> None:
        self._user_repo = user_repo
        self._totp = totp_handler
        self._enc = encryption

    async def execute(self, user_id: uuid.UUID, code: str) -> None:
        """Verify the TOTP code and enable 2FA for the user."""
        user = await self._user_repo.get_by_id(user_id)
        if not user or not user.totp_secret_encrypted:
            raise InvalidCredentialsError("TOTP not set up.")

        secret = self._enc.decrypt_string(user.totp_secret_encrypted)
        if not self._totp.verify(secret, code):
            raise InvalidTOTPError()

        user.totp_enabled = True
        user.updated_at = datetime.datetime.now(datetime.timezone.utc)
        await self._user_repo.update(user)
        logger.info("totp_enabled", user_id=str(user_id))


class VerifyTOTP:
    """Verify TOTP during login (after password step)."""

    def __init__(
        self,
        user_repo: AbstractUserRepository,
        totp_handler: TOTPHandler,
        encryption: AESEncryption,
        jwt_handler: JWTHandler,
    ) -> None:
        self._user_repo = user_repo
        self._totp = totp_handler
        self._enc = encryption
        self._jwt = jwt_handler

    async def execute(self, user_id: uuid.UUID, code: str) -> dict[str, Any]:
        """Verify TOTP code and return full access token."""
        user = await self._user_repo.get_by_id(user_id)
        if not user or not user.totp_secret_encrypted:
            raise InvalidCredentialsError("TOTP not configured.")

        secret = self._enc.decrypt_string(user.totp_secret_encrypted)
        if not self._totp.verify(secret, code):
            raise InvalidTOTPError()

        access_token = self._jwt.create_access_token(user.id)

        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user_id": str(user.id),
        }
