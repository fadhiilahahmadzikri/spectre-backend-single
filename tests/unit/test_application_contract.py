import uuid

import pytest

from spectre.domain.entities.tenant_application import TenantApplication
from spectre.interface.routers.application_router import _app_to_response
from spectre.interface.schemas.application_schema import (
    CreateApplicationRequest,
    UpdateApplicationRequest,
)


REMOVED_CALLBACK_PREFIX = "web" + "hook"
REMOVED_CALLBACK_URL_FIELD = f"{REMOVED_CALLBACK_PREFIX}_url"


def test_application_response_excludes_removed_callback_fields() -> None:
    app = TenantApplication(
        id=uuid.uuid4(),
        owner_id=uuid.uuid4(),
        name="Production app",
    )

    response = _app_to_response(app)

    assert response["name"] == "Production app"
    assert REMOVED_CALLBACK_URL_FIELD not in response
    assert f"has_{REMOVED_CALLBACK_PREFIX}" not in response
    assert f"{REMOVED_CALLBACK_PREFIX}_secret" not in response


@pytest.mark.parametrize("request_cls", [CreateApplicationRequest, UpdateApplicationRequest])
def test_application_requests_reject_removed_callback_url(request_cls) -> None:
    with pytest.raises(ValueError):
        request_cls(
            name="Production app",
            **{REMOVED_CALLBACK_URL_FIELD: "https://client.example.com/events"},
        )
