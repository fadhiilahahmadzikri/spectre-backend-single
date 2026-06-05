"""Celery application factory and task registration."""

from __future__ import annotations

from celery import Celery

from spectre.config import get_settings

settings = get_settings()

celery_app = Celery(
    "spectre",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
)

# Register task modules explicitly. Celery autodiscovery only imports the package
# and can miss nested modules when workers start from this app object.
import spectre.workers.tasks.webhook_task  # noqa: E402, F401

# Register Celery lifecycle signal handlers (logging)
import spectre.workers.signals  # noqa: E402, F401
