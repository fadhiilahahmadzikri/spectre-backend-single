"""API key management use cases."""

from __future__ import annotations

import uuid

from spectre.config import Settings
from spectre.core.logger import get_logger
from spectre.domain.entities.api_key import ApiKey
from spectre.domain.exceptions.tenant_exceptions import ApplicationNotFoundError, ForbiddenError
from spectre.domain.ports.repositories import (
    AbstractApiKeyRepository,
    AbstractTenantApplicationRepository,
)
from spectre.domain.value_objects.api_key_pair import ApiKeyPair
from spectre.infrastructure.security.api_key_generator import ApiKeyGenerator

logger = get_logger(__name__)


class GenerateApiKey:
    def __init__(self, api_key_repo: AbstractApiKeyRepository, app_repo: AbstractTenantApplicationRepository, key_generator: ApiKeyGenerator) -> None:
        self._api_key_repo = api_key_repo
        self._app_repo = app_repo
        self._keygen = key_generator

    async def execute(self, app_id: uuid.UUID, owner_id: uuid.UUID, label: str | None = None) -> tuple[ApiKey, str]:
        app = await self._app_repo.get_by_id(app_id)
        if not app or app.status == "deleted":
            raise ApplicationNotFoundError()
        if app.owner_id != owner_id:
            raise ForbiddenError()
        pair: ApiKeyPair = self._keygen.generate()
        api_key = ApiKey(id=uuid.uuid4(), app_id=app_id, key_prefix=pair.prefix, key_hash=pair.key_hash, label=label)
        api_key = await self._api_key_repo.create(api_key)
        logger.info("api_key_generated", app_id=str(app_id), key_prefix=pair.prefix)
        return api_key, pair.full_key


class ListApiKeys:
    def __init__(self, api_key_repo: AbstractApiKeyRepository, app_repo: AbstractTenantApplicationRepository) -> None:
        self._api_key_repo = api_key_repo
        self._app_repo = app_repo

    async def execute(self, app_id: uuid.UUID, owner_id: uuid.UUID) -> list[ApiKey]:
        app = await self._app_repo.get_by_id(app_id)
        if not app or app.status == "deleted":
            raise ApplicationNotFoundError()
        if app.owner_id != owner_id:
            raise ForbiddenError()
        return await self._api_key_repo.list_by_app(app_id)


class RevokeApiKey:
    def __init__(self, api_key_repo: AbstractApiKeyRepository, app_repo: AbstractTenantApplicationRepository) -> None:
        self._api_key_repo = api_key_repo
        self._app_repo = app_repo

    async def execute(self, key_id: uuid.UUID, app_id: uuid.UUID, owner_id: uuid.UUID) -> None:
        app = await self._app_repo.get_by_id(app_id)
        if not app or app.status == "deleted":
            raise ApplicationNotFoundError()
        if app.owner_id != owner_id:
            raise ForbiddenError()
        api_key = await self._api_key_repo.get_by_id(key_id)
        if not api_key or api_key.app_id != app_id:
            raise ApplicationNotFoundError("API key not found.")
        await self._api_key_repo.revoke(key_id)
        logger.info("api_key_revoked", key_id=str(key_id))
