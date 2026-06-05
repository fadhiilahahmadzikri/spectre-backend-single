"""Base exception for all Spectre domain errors.

All domain exceptions inherit from SpectreError and carry a machine-readable
error_code and the appropriate HTTP status code for the API layer.
"""

from __future__ import annotations


class SpectreError(Exception):
    """Base exception for all Spectre errors.

    Attributes:
        error_code: Machine-readable error identifier (e.g., 'FACE_NOT_FOUND').
        message: Human-readable description.
        http_status: HTTP status code to return from the API.
        details: Optional additional context.
    """

    error_code: str = "INTERNAL_ERROR"
    http_status: int = 500

    def __init__(
        self,
        message: str = "An internal error occurred.",
        *,
        details: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details
