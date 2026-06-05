"""SQLAlchemy engine event listeners for query observability.

Hooks into ``before_cursor_execute``, ``after_cursor_execute``, and
``handle_error`` engine events to log every SQL operation transparently.
No repository or model code changes required.

Features:
    - Query duration tracking (ms)
    - Slow query detection (configurable threshold, default 500ms)
    - Error logging with full exception trace
    - Operation type extraction (SELECT, INSERT, UPDATE, DELETE)
"""

from __future__ import annotations

import time

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine

from spectre.core.logger import get_logger

logger = get_logger("db.sqlalchemy")

# Default slow query threshold (overridden by Settings at attach time)
_SLOW_QUERY_THRESHOLD_MS: int = 500


def attach_query_logging(
    engine: AsyncEngine,
    *,
    slow_query_threshold_ms: int = 500,
) -> None:
    """Register SQLAlchemy event listeners on the async engine.

    Args:
        engine: The async SQLAlchemy engine to instrument.
        slow_query_threshold_ms: Queries slower than this are logged as WARNING.
    """
    global _SLOW_QUERY_THRESHOLD_MS
    _SLOW_QUERY_THRESHOLD_MS = slow_query_threshold_ms

    sync_engine = engine.sync_engine

    @event.listens_for(sync_engine, "before_cursor_execute")
    def _before_cursor_execute(
        conn, cursor, statement, parameters, context, executemany
    ):
        conn.info.setdefault("query_start_time", []).append(time.perf_counter())

    @event.listens_for(sync_engine, "after_cursor_execute")
    def _after_cursor_execute(
        conn, cursor, statement, parameters, context, executemany
    ):
        start_times = conn.info.get("query_start_time")
        if not start_times:
            return

        duration_ms = round((time.perf_counter() - start_times.pop()) * 1000, 2)
        op = statement.strip().split()[0].upper() if statement else "UNKNOWN"

        bound = logger.bind(
            db_operation=op,
            duration_ms=duration_ms,
            rows=cursor.rowcount if cursor.rowcount >= 0 else 0,
        )

        if duration_ms >= _SLOW_QUERY_THRESHOLD_MS:
            bound.bind(
                sql=statement[:500] if statement else "",
                slow_query=True,
            ).warning(
                "Slow query detected | {}ms (threshold={}ms)",
                duration_ms,
                _SLOW_QUERY_THRESHOLD_MS,
            )
        else:
            bound.debug("Query completed | {} | {}ms", op, duration_ms)

    @event.listens_for(sync_engine, "handle_error")
    def _handle_error(exception_context):
        logger.bind(
            sql=str(exception_context.statement)[:500] if exception_context.statement else "",
            params=str(exception_context.parameters)[:200] if exception_context.parameters else "",
        ).exception(
            "SQL error | {}",
            exception_context.original_exception,
        )

    logger.info(
        "Query logging attached | slow_threshold={}ms",
        _SLOW_QUERY_THRESHOLD_MS,
    )
