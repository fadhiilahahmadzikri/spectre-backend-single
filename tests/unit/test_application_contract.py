import uuid

import pytest

from spectre.domain.entities.tenant_application import TenantApplication
from spectre.interface.routers.application_router import _app_to_response
from spectre.interface.schemas.application_schema import (
    CreateApplicationRequest,
    UpdateApplicationRequest,
)


def test_application_response_excludes_removed_webhook_fields() -> None:
    app = TenantApplication(
        id=uuid.uuid4(),
        owner_id=uuid.uuid4(),
        name="Production app",
    )

    response = _app_to_response(app)

    assert response["name"] == "Production app"
    assert "webhook_url" not in response
    assert "has_webhook" not in response
    assert "webhook_secret" not in response


@pytest.mark.parametrize("request_cls", [CreateApplicationRequest, UpdateApplicationRequest])
def test_application_requests_reject_removed_webhook_url(request_cls) -> None:
    with pytest.raises(ValueError):
        request_cls(name="Production app", webhook_url="https://client.example.com/events")
