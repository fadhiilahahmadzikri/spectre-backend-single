"""Celery task modules.

Import task modules here so Celery registers them when the worker starts with
`-A spectre.workers.celery_app`.
"""

from spectre.workers.tasks import webhook_task as webhook_task
