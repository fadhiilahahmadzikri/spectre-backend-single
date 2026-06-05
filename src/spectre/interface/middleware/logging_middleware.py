"""HTTP request/response logging middleware.

Logs every incoming request and outgoing response with structured context:
method, path, status_code, duration_ms, client_ip, request_id.

Writes to both the main app sink and the dedicated access log sink.
"""

from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from spectre.core.logger import get_logger

logger = get_logger("middleware.http")


class LoggingMiddleware(BaseHTTPMiddleware):
    """Log HTTP lifecycle events for every request."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = getattr(request.state, "request_id", "unknown")
        start = time.perf_counter()

        req_logger = logger.bind(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            client_ip=request.client.host if request.client else "unknown",
        )

        req_logger.info("Request received")

        try:
            response = await call_next(request)
            duration_ms = round((time.perf_counter() - start) * 1000, 2)

            level = "warning" if response.status_code >= 400 else "info"
            getattr(req_logger.bind(
                status_code=response.status_code,
                duration_ms=duration_ms,
            ), level)("Request completed")

            return response

        except Exception as exc:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            req_logger.bind(duration_ms=duration_ms).exception(
                "Request failed | error={}: {}", type(exc).__name__, exc
            )
            raise
