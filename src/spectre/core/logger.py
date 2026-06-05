"""Centralized logging infrastructure — single source of truth.

All modules import from here. Never instantiate loguru directly elsewhere.

Architecture:
    setup_logging()  →  called ONCE at application startup
    get_logger(name) →  returns a named, bound loguru logger

Sinks:
    Console   — pretty-printed (dev) or JSON (production)
    App file  — logs/app/{date}.log  (daily rotation, gz, 30d retention)
    Error file — logs/error/{date}.error.log  (ERROR+ only)
    Access file — logs/access/{date}.access.log (HTTP events)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from loguru import logger


# ---------------------------------------------------------------------------
# Log directory setup
# ---------------------------------------------------------------------------

LOG_DIR = Path("logs")


def _ensure_log_dirs() -> None:
    """Create log subdirectories if they don't exist."""
    for sub in ("app", "error", "access", "client"):
        (LOG_DIR / sub).mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# JSON serializer for production file/console output
# ---------------------------------------------------------------------------


def _json_serializer(record: dict[str, Any]) -> str:
    """Serialize a loguru record to a single JSON line."""
    log_entry: dict[str, Any] = {
        "timestamp": record["time"].strftime("%Y-%m-%dT%H:%M:%S.%f%z"),
        "level": record["level"].name,
        "logger": record.get("name", ""),
        "message": record["message"],
        "module": record.get("module", ""),
        "function": record.get("function", ""),
        "line": record.get("line", 0),
    }

    # Attach structured context (bound via .bind())
    extra = record.get("extra", {})
    if extra:
        log_entry["context"] = {k: v for k, v in extra.items() if v is not None}

    # Attach exception info when present
    exc = record.get("exception")
    if exc is not None:
        log_entry["exception"] = {
            "type": exc.type.__name__ if exc.type else None,
            "value": str(exc.value) if exc.value else None,
            "traceback": True,
        }

    return json.dumps(log_entry, default=str)


def _json_sink(message: Any) -> None:
    """Console sink that emits one JSON line per log event."""
    record = message.record
    print(_json_serializer(record), file=sys.stdout, flush=True)


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

_LOG_FORMAT = (
    "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
    "{name}:{function}:{line} | {message}"
)

_CONSOLE_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
    "<level>{message}</level>"
)


def setup_logging(
    *,
    app_name: str = "spectre",
    log_level: str = "INFO",
    is_production: bool = False,
    retention: str = "30 days",
    diagnose: bool | None = None,
) -> None:
    """Initialize the loguru logging system.

    Call this **once** at application startup (lifespan or worker boot).

    Args:
        app_name: Application identifier for log context.
        log_level: Minimum log level (TRACE/DEBUG/INFO/WARNING/ERROR/CRITICAL).
        is_production: If True, uses JSON console sink and disables diagnose.
        retention: How long to keep rotated log files.
        diagnose: Show local variable values in tracebacks. Defaults to
                  True in dev, False in production (PII protection).
    """
    logger.remove()  # Clear default handler

    if diagnose is None:
        diagnose = not is_production

    _ensure_log_dirs()

    # ── Console sink ──────────────────────────────────────────────────────
    if is_production:
        logger.add(_json_sink, level=log_level, colorize=False)
    else:
        logger.add(
            sys.stdout,
            format=_CONSOLE_FORMAT,
            level=log_level,
            colorize=True,
            backtrace=True,
            diagnose=diagnose,
        )

    # ── App file sink (all events) ────────────────────────────────────────
    logger.add(
        str(LOG_DIR / "app" / "{time:YYYY-MM-DD}.log"),
        format=_LOG_FORMAT,
        level=log_level,
        rotation="00:00",
        retention=retention,
        compression="gz",
        backtrace=True,
        diagnose=diagnose,
        enqueue=True,
    )

    # ── Error file sink (ERROR and above only) ────────────────────────────
    logger.add(
        str(LOG_DIR / "error" / "{time:YYYY-MM-DD}.error.log"),
        format=_LOG_FORMAT,
        level="ERROR",
        rotation="00:00",
        retention=retention,
        compression="gz",
        backtrace=True,
        diagnose=diagnose,
        enqueue=True,
    )

    # ── Access file sink (HTTP request/response events) ───────────────────
    logger.add(
        str(LOG_DIR / "access" / "{time:YYYY-MM-DD}.access.log"),
        format=_LOG_FORMAT,
        level="INFO",
        rotation="00:00",
        retention=retention,
        compression="gz",
        enqueue=True,
        filter=lambda record: record["extra"].get("logger_name", "").startswith(
            "middleware"
        ),
    )

    # ── Client file sink (Frontend/POC telemetry) ─────────────────────────
    logger.add(
        str(LOG_DIR / "client" / "{time:YYYY-MM-DD}.client.log"),
        format=_LOG_FORMAT,
        level="INFO",
        rotation="00:00",
        retention=retention,
        compression="gz",
        enqueue=True,
        filter=lambda record: record["extra"].get("client_log", False),
    )

    logger.info(
        "Logging initialized | app={} | level={} | dir={}",
        app_name,
        log_level,
        LOG_DIR.resolve(),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_logger(name: str) -> Any:
    """Return a named loguru logger with ``logger_name`` bound.

    Usage::

        from spectre.core.logger import get_logger
        logger = get_logger(__name__)
        logger.info("Something happened", extra_key="value")

    Args:
        name: Module or component name (typically ``__name__``).

    Returns:
        A loguru BoundLogger with the ``logger_name`` context field set.
    """
    return logger.bind(logger_name=name)
