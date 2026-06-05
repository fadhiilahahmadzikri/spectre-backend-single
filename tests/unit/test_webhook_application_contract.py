import uuid

import pytest

from spectre.domain.entities.tenant_application import TenantApplication
from spectre.interface.routers.application_router import _app_to_response
from spectre.interface.schemas.application_schema import (
    CreateApplicationRequest,
    UpdateApplicationRequest,
)
from spectre.workers.celery_app import celery_app


def test_application_response_exposes_webhook_status() -> None:
    app = TenantApplication(
        id=uuid.uuid4(),
        owner_id=uuid.uuid4(),
        name="Production app",
        webhook_url="https://client.example.com/webhooks/spectre",
        webhook_secret_encrypted="encrypted-secret",
    )

    response = _app_to_response(app)

    assert response["webhook_url"] == "https://client.example.com/webhooks/spectre"
    assert response["has_webhook"] is True


def test_application_request_normalizes_blank_webhook_url() -> None:
    create_request = CreateApplicationRequest(
        name="Production app",
        webhook_url="   ",
    )
    update_request = UpdateApplicationRequest(webhook_url="   ")

    assert create_request.webhook_url is None
    assert update_request.webhook_url is None


@pytest.mark.parametrize("request_cls", [CreateApplicationRequest, UpdateApplicationRequest])
def test_application_request_rejects_relative_webhook_url(request_cls) -> None:
    with pytest.raises(ValueError):
        request_cls(name="Production app", webhook_url="/webhooks/spectre")


def test_webhook_delivery_task_is_registered() -> None:
    assert (
        "spectre.workers.tasks.webhook_task.deliver_webhook" in celery_app.tasks
    )
