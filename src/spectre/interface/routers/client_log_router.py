"""Client Telemetry Router.

Allows client applications to push errors and logs to the backend securely.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status

from spectre.core.logger import get_logger
from spectre.interface.dependencies import AuthenticatedApp
from spectre.interface.schemas.client_log_schema import ClientLogRequest

router = APIRouter(prefix="/api/v1", tags=["Telemetry"])
logger = get_logger(__name__)


@router.post("/client-logs", status_code=status.HTTP_202_ACCEPTED, response_model=dict)
async def ingest_client_log(
    request: Request,
    body: ClientLogRequest,
    app: AuthenticatedApp,  # Requires X-API-Key
) -> dict:
    """Ingest frontend telemetry, logs, and errors.

    Ensures that frontend errors are centralized in the backend logs
    and tied to the specific tenant application via X-API-Key.
    """
    # Create a specialized logger instance strictly for client logs
    client_logger = logger.bind(
        client_log=True,
        app_id=str(app.id),
        source=body.source,
        client_ip=request.client.host if request.client else "unknown",
    )

    lvl = body.level.lower()
    msg = body.message
    ctx = body.context or {}

    # Map the level
    if lvl in ("error", "err", "exception"):
        client_logger.error("client_error | {} | {}", msg, ctx)
    elif lvl in ("warn", "warning"):
        client_logger.warning("client_warning | {} | {}", msg, ctx)
    elif lvl in ("info", "log"):
        client_logger.info("client_info | {} | {}", msg, ctx)
    else:
        # Default to info if unknown level
        client_logger.info("client_log | [{}] {} | {}", lvl, msg, ctx)

    return {"status": "accepted"}
