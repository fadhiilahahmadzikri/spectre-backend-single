"""Authentication-related domain exceptions."""

from __future__ import annotations

from spectre.domain.exceptions.base import SpectreError


class InvalidCredentialsError(SpectreError):
    error_code = "INVALID_CREDENTIALS"
    http_status = 401

    def __init__(self, message: str = "Invalid email or password.") -> None:
        super().__init__(message)


class EmailAlreadyRegisteredError(SpectreError):
    error_code = "EMAIL_ALREADY_REGISTERED"
    http_status = 409

    def __init__(self, message: str = "An account with this email already exists.") -> None:
        super().__init__(message)


class TOTPRequiredError(SpectreError):
    error_code = "TOTP_REQUIRED"
    http_status = 403

    def __init__(self, message: str = "TOTP verification is required.") -> None:
        super().__init__(message)


class InvalidTOTPError(SpectreError):
    error_code = "INVALID_TOTP"
    http_status = 400

    def __init__(self, message: str = "Invalid TOTP code.") -> None:
        super().__init__(message)


class InvalidRefreshTokenError(SpectreError):
    error_code = "INVALID_REFRESH_TOKEN"
    http_status = 401

    def __init__(self, message: str = "Invalid or expired refresh token.") -> None:
        super().__init__(message)


class AccountDisabledError(SpectreError):
    error_code = "ACCOUNT_DISABLED"
    http_status = 403

    def __init__(self, message: str = "Account has been disabled.") -> None:
        super().__init__(message)


class InvalidTokenError(SpectreError):
    error_code = "INVALID_TOKEN"
    http_status = 401

    def __init__(self, message: str = "Invalid or expired token.") -> None:
        super().__init__(message)
