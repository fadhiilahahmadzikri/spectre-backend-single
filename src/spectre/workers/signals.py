"""Celery signal handlers for task lifecycle observability.

Imported by ``celery_app.py`` to register signal hooks automatically.
Logs task start, completion, failure, retry, and worker lifecycle events.
"""

from __future__ import annotations

from celery.signals import (
    task_failure,
    task_postrun,
    task_prerun,
    task_retry,
    worker_ready,
    worker_shutdown,
)

from spectre.core.logger import get_logger, setup_logging

logger = get_logger("celery.worker")


@worker_ready.connect
def on_worker_ready(sender, **kwargs):  # type: ignore[no-untyped-def]
    """Initialize logging when the Celery worker boots."""
    from spectre.config import get_settings

    settings = get_settings()
    setup_logging(
        app_name="spectre-worker",
        log_level=settings.log_level,
        is_production=settings.is_production,
        retention=settings.log_retention,
    )
    logger.info("Celery worker ready")


@worker_shutdown.connect
def on_worker_shutdown(sender, **kwargs):  # type: ignore[no-untyped-def]
    logger.info("Celery worker shutdown")


@task_prerun.connect
def on_task_prerun(task_id, task, args, kwargs, **extra):  # type: ignore[no-untyped-def]
    logger.bind(
        task_id=task_id,
        task_name=task.name,
        args=str(args)[:200],
        kwargs=str(kwargs)[:200],
    ).info("Task started")


@task_postrun.connect
def on_task_postrun(task_id, task, retval, state, **kwargs):  # type: ignore[no-untyped-def]
    logger.bind(
        task_id=task_id,
        task_name=task.name,
        state=state,
    ).info("Task completed")


@task_failure.connect
def on_task_failure(task_id, exception, traceback, einfo, **kwargs):  # type: ignore[no-untyped-def]
    logger.bind(
        task_id=task_id,
        error_type=type(exception).__name__,
        error=str(exception),
    ).exception("Task failed | error={}", exception)


@task_retry.connect
def on_task_retry(request, reason, einfo, **kwargs):  # type: ignore[no-untyped-def]
    logger.bind(
        task_id=request.id,
        reason=str(reason),
        retries=request.retries,
    ).warning("Task retrying")
