"""Abstract repository ports — define data access contracts.

Infrastructure layer provides SQL implementations. Domain and application
layers depend only on these abstractions.
"""

from __future__ import annotations

import datetime
from abc import ABC, abstractmethod
from typing import Any
from uuid import UUID

from spectre.domain.entities.api_key import ApiKey
from spectre.domain.entities.auth_session import AuthSession
from spectre.domain.entities.face_profile import FaceProfile
from spectre.domain.entities.refresh_token import RefreshToken
from spectre.domain.entities.tenant_application import TenantApplication
from spectre.domain.entities.user import User, UserIdentity
from spectre.domain.entities.webhook_delivery import WebhookDelivery


class AbstractUserRepository(ABC):
    """Data access contract for User entities."""

    @abstractmethod
    async def create(self, user: User) -> User: ...

    @abstractmethod
    async def get_by_id(self, user_id: UUID) -> User | None: ...

    @abstractmethod
    async def get_by_email(self, email: str) -> User | None: ...

    @abstractmethod
    async def update(self, user: User) -> User: ...

    @abstractmethod
    async def get_identity(self, provider: str, provider_user_id: str) -> UserIdentity | None: ...

    @abstractmethod
    async def get_identities_by_user(self, user_id: UUID) -> list[UserIdentity]: ...

    @abstractmethod
    async def create_identity(self, identity: UserIdentity) -> UserIdentity: ...

    @abstractmethod
    async def update_identity(self, identity: UserIdentity) -> UserIdentity: ...


class AbstractTenantApplicationRepository(ABC):
    """Data access contract for TenantApplication entities."""

    @abstractmethod
    async def create(self, app: TenantApplication) -> TenantApplication: ...

    @abstractmethod
    async def get_by_id(self, app_id: UUID) -> TenantApplication | None: ...

    @abstractmethod
    async def list_by_owner(
        self, owner_id: UUID, *, offset: int = 0, limit: int = 50
    ) -> list[TenantApplication]: ...

    @abstractmethod
    async def update(self, app: TenantApplication) -> TenantApplication: ...

    @abstractmethod
    async def soft_delete(self, app_id: UUID) -> None: ...


class AbstractApiKeyRepository(ABC):
    """Data access contract for ApiKey entities."""

    @abstractmethod
    async def create(self, api_key: ApiKey) -> ApiKey: ...

    @abstractmethod
    async def get_by_id(self, key_id: UUID) -> ApiKey | None: ...

    @abstractmethod
    async def get_by_prefix(self, prefix: str) -> ApiKey | None: ...

    @abstractmethod
    async def list_by_app(self, app_id: UUID) -> list[ApiKey]: ...

    @abstractmethod
    async def revoke(self, key_id: UUID) -> None: ...

    @abstractmethod
    async def delete(self, key_id: UUID) -> None: ...

    @abstractmethod
    async def update_last_used(self, key_id: UUID) -> None: ...


class AbstractFaceProfileRepository(ABC):
    """Data access contract for FaceProfile entities."""

    @abstractmethod
    async def create(self, profile: FaceProfile) -> FaceProfile: ...

    @abstractmethod
    async def get_by_external_user(
        self, app_id: UUID, external_user_id: str
    ) -> FaceProfile | None: ...

    @abstractmethod
    async def exists(
        self, app_id: UUID, external_user_id: str
    ) -> bool: ...

    @abstractmethod
    async def update(self, profile: FaceProfile) -> FaceProfile: ...

    @abstractmethod
    async def delete(self, app_id: UUID, external_user_id: str) -> None: ...

    @abstractmethod
    async def list_by_app(
        self, app_id: UUID, *, offset: int = 0, limit: int = 50
    ) -> list[FaceProfile]: ...

    @abstractmethod
    async def delete_all(self, app_id: UUID) -> int: ...


class AbstractAuthSessionRepository(ABC):
    """Data access contract for AuthSession entities."""

    @abstractmethod
    async def create(self, session: AuthSession) -> AuthSession: ...

    @abstractmethod
    async def get_by_id(self, session_id: UUID) -> AuthSession | None: ...

    @abstractmethod
    async def update(self, session: AuthSession) -> AuthSession: ...

    @abstractmethod
    async def list_by_app(
        self,
        app_id: UUID,
        *,
        offset: int = 0,
        limit: int = 50,
        status: str | None = None,
    ) -> list[AuthSession]: ...


class AbstractWebhookDeliveryRepository(ABC):
    """Data access contract for WebhookDelivery entities."""

    @abstractmethod
    async def create(self, delivery: WebhookDelivery) -> WebhookDelivery: ...

    @abstractmethod
    async def get_by_id(self, delivery_id: UUID) -> WebhookDelivery | None: ...

    @abstractmethod
    async def update(self, delivery: WebhookDelivery) -> WebhookDelivery: ...

    @abstractmethod
    async def list_by_app(
        self, app_id: UUID, *, offset: int = 0, limit: int = 50
    ) -> list[WebhookDelivery]: ...

    @abstractmethod
    async def get_pending_retries(
        self, before: datetime.datetime
    ) -> list[WebhookDelivery]: ...


class AbstractRefreshTokenRepository(ABC):
    """Data access contract for RefreshToken entities."""

    @abstractmethod
    async def create(self, token: RefreshToken) -> RefreshToken: ...

    @abstractmethod
    async def get_by_hash(self, token_hash: str) -> RefreshToken | None: ...

    @abstractmethod
    async def revoke(self, token_id: UUID) -> None: ...

    @abstractmethod
    async def revoke_all_for_user(self, user_id: UUID) -> None: ...


class AbstractAuditLogRepository(ABC):
    """Data access contract for append-only audit logs."""

    @abstractmethod
    async def append(
        self,
        *,
        event_type: str,
        app_id: UUID | None = None,
        user_id: UUID | None = None,
        api_key_id: UUID | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        ip_address: str | None = None,
    ) -> None: ...


class AbstractConfigRepository(ABC):
    """Data access contract for system configuration parameters."""

    @abstractmethod
    async def get_all(self) -> list[dict[str, Any]]: ...

    @abstractmethod
    async def get_by_category(self, category: str) -> list[dict[str, Any]]: ...

    @abstractmethod
    async def get_by_key(self, key: str) -> dict[str, Any] | None: ...

    @abstractmethod
    async def update_value(self, key: str, value: str, updated_by: UUID | None = None) -> dict[str, Any] | None: ...
