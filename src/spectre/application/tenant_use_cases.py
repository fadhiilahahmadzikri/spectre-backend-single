"""Tenant application management use cases."""

from __future__ import annotations

import datetime
import secrets
import uuid

from spectre.config import Settings
from spectre.core.logger import get_logger
from spectre.domain.entities.tenant_application import TenantApplication
from spectre.domain.exceptions.tenant_exceptions import ApplicationNotFoundError, ForbiddenError
from spectre.domain.ports.repositories import AbstractTenantApplicationRepository
from spectre.infrastructure.security.aes_encryption import AESEncryption

logger = get_logger(__name__)


class CreateApplication:
    """Create a new tenant application."""

    def __init__(
        self,
        app_repo: AbstractTenantApplicationRepository,
        encryption: AESEncryption,
        settings: Settings,
    ) -> None:
        self._app_repo = app_repo
        self._enc = encryption
        self._settings = settings

    async def execute(
        self,
        owner_id: uuid.UUID,
        name: str,
        webhook_url: str | None = None,
    ) -> TenantApplication:
        """Create a new application with optional webhook config."""
        webhook_secret = None
        webhook_secret_encrypted = None

        if webhook_url:
            webhook_secret = secrets.token_urlsafe(32)
            webhook_secret_encrypted = self._enc.encrypt_string(webhook_secret)

        app = TenantApplication(
            id=uuid.uuid4(),
            owner_id=owner_id,
            name=name,
            webhook_url=webhook_url,
            webhook_secret_encrypted=webhook_secret_encrypted,
            liveness_threshold=self._settings.liveness_threshold,
            similarity_threshold=self._settings.similarity_threshold,
        )
        app = await self._app_repo.create(app)
        logger.info("application_created", app_id=str(app.id), name=name)
        return app


class ListApplications:
    """List applications owned by a user."""

    def __init__(self, app_repo: AbstractTenantApplicationRepository) -> None:
        self._app_repo = app_repo

    async def execute(
        self, owner_id: uuid.UUID, *, offset: int = 0, limit: int = 50
    ) -> list[TenantApplication]:
        return await self._app_repo.list_by_owner(owner_id, offset=offset, limit=limit)


class GetApplication:
    """Get a specific application by ID."""

    def __init__(self, app_repo: AbstractTenantApplicationRepository) -> None:
        self._app_repo = app_repo

    async def execute(
        self, app_id: uuid.UUID, owner_id: uuid.UUID
    ) -> TenantApplication:
        app = await self._app_repo.get_by_id(app_id)
        if not app or app.status == "deleted":
            raise ApplicationNotFoundError()
        if app.owner_id != owner_id:
            raise ForbiddenError("You do not own this application.")
        return app


class UpdateApplication:
    """Update application settings."""

    def __init__(
        self,
        app_repo: AbstractTenantApplicationRepository,
        encryption: AESEncryption,
    ) -> None:
        self._app_repo = app_repo
        self._enc = encryption

    async def execute(
        self,
        app_id: uuid.UUID,
        owner_id: uuid.UUID,
        *,
        name: str | None = None,
        webhook_url: str | None = None,
        liveness_threshold: float | None = None,
        similarity_threshold: float | None = None,
        allowed_ips: list[str] | None = None,
    ) -> TenantApplication:
        app = await self._app_repo.get_by_id(app_id)
        if not app or app.status == "deleted":
            raise ApplicationNotFoundError()
        if app.owner_id != owner_id:
            raise ForbiddenError()

        if name is not None:
            app.name = name
        if webhook_url is not None:
            app.webhook_url = webhook_url
            webhook_secret = secrets.token_urlsafe(32)
            app.webhook_secret_encrypted = self._enc.encrypt_string(webhook_secret)
        if liveness_threshold is not None:
            app.liveness_threshold = liveness_threshold
        if similarity_threshold is not None:
            app.similarity_threshold = similarity_threshold
        if allowed_ips is not None:
            app.allowed_ips = allowed_ips

        app.updated_at = datetime.datetime.now(datetime.timezone.utc)
        app = await self._app_repo.update(app)
        logger.info("application_updated", app_id=str(app_id))
        return app


class DeleteApplication:
    """Soft-delete an application."""

    def __init__(self, app_repo: AbstractTenantApplicationRepository) -> None:
        self._app_repo = app_repo

    async def execute(self, app_id: uuid.UUID, owner_id: uuid.UUID) -> None:
        app = await self._app_repo.get_by_id(app_id)
        if not app or app.status == "deleted":
            raise ApplicationNotFoundError()
        if app.owner_id != owner_id:
            raise ForbiddenError()

        await self._app_repo.soft_delete(app_id)
        logger.info("application_deleted", app_id=str(app_id))
