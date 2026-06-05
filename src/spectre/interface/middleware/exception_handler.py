"""Exception handler — maps domain exceptions to HTTP responses."""

from __future__ import annotations

import datetime

from fastapi import Request
from fastapi.responses import JSONResponse

from spectre.domain.exceptions.base import SpectreError


async def spectre_exception_handler(request: Request, exc: SpectreError) -> JSONResponse:
    """Convert SpectreError subclasses into standard error responses."""
    request_id = getattr(request.state, "request_id", None)
    return JSONResponse(
        status_code=exc.http_status,
        content={
            "success": False,
            "error": {
                "code": exc.error_code,
                "message": exc.message,
                "details": exc.details,
            },
            "request_id": request_id,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        },
    )
