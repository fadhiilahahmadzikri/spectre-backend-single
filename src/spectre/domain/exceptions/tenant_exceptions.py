"""Tenant and API key domain exceptions."""

from __future__ import annotations

from spectre.domain.exceptions.base import SpectreError


class ApplicationNotFoundError(SpectreError):
    error_code = "APPLICATION_NOT_FOUND"
    http_status = 404

    def __init__(self, message: str = "Application not found.") -> None:
        super().__init__(message)


class DuplicateApplicationNameError(SpectreError):
    error_code = "DUPLICATE_APP_NAME"
    http_status = 409

    def __init__(
        self,
        message: str = "An application with this name already exists under your account.",
    ) -> None:
        super().__init__(message)


class ApplicationSuspendedError(SpectreError):
    error_code = "APPLICATION_SUSPENDED"
    http_status = 403

    def __init__(self, message: str = "Application has been suspended.") -> None:
        super().__init__(message)


class InvalidApiKeyError(SpectreError):
    error_code = "INVALID_API_KEY"
    http_status = 401

    def __init__(self, message: str = "Invalid or missing API key.") -> None:
        super().__init__(message)


class ApiKeyRevokedError(SpectreError):
    error_code = "API_KEY_REVOKED"
    http_status = 401

    def __init__(self, message: str = "API key has been revoked.") -> None:
        super().__init__(message)


class RateLimitExceededError(SpectreError):
    error_code = "RATE_LIMIT_EXCEEDED"
    http_status = 429

    def __init__(self, message: str = "Rate limit exceeded. Please retry later.") -> None:
        super().__init__(message)


class IPNotAllowedError(SpectreError):
    error_code = "IP_NOT_ALLOWED"
    http_status = 403

    def __init__(self, message: str = "Request IP is not in the allowed list.") -> None:
        super().__init__(message)


class SessionNotFoundError(SpectreError):
    error_code = "SESSION_NOT_FOUND"
    http_status = 404

    def __init__(self, message: str = "Session not found.") -> None:
        super().__init__(message)


class SessionExpiredError(SpectreError):
    error_code = "SESSION_EXPIRED"
    http_status = 410

    def __init__(self, message: str = "Session has expired.") -> None:
        super().__init__(message)


class ForbiddenError(SpectreError):
    error_code = "FORBIDDEN"
    http_status = 403

    def __init__(self, message: str = "Access denied.") -> None:
        super().__init__(message)
