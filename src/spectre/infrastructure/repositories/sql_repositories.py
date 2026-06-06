"""SQL repository implementations for all domain entities.

Each repository maps between domain entities and ORM models,
ensuring clean separation of concerns.
"""

from __future__ import annotations

import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select, update, delete, and_
from sqlalchemy.ext.asyncio import AsyncSession

from spectre.domain.entities.api_key import ApiKey
from spectre.domain.entities.auth_session import AuthSession
from spectre.domain.entities.face_profile import FaceProfile
from spectre.domain.entities.refresh_token import RefreshToken
from spectre.domain.entities.tenant_application import TenantApplication
from spectre.domain.entities.user import User, UserIdentity
from spectre.domain.ports.repositories import (
    AbstractApiKeyRepository,
    AbstractAuditLogRepository,
    AbstractAuthSessionRepository,
    AbstractConfigRepository,
    AbstractFaceProfileRepository,
    AbstractRefreshTokenRepository,
    AbstractTenantApplicationRepository,
    AbstractUserRepository,
)
from spectre.infrastructure.database.models.tables import (
    ApiKeyModel,
    AuditLogModel,
    AuthSessionModel,
    FaceProfileModel,
    RefreshTokenModel,
    SpectreEventModel,
    TenantApplicationModel,
    WebhookDeliveryModel,
    WebhookEndpointModel,
    UserModel,
    UserIdentityModel,
    SystemConfigModel,
)


# =============================================================================
# Mappers (ORM ↔ Domain Entity)
# =============================================================================


def _user_to_entity(m: UserModel) -> User:
    return User(
        id=m.id,
        email=m.email,
        display_name=m.display_name,
        totp_secret_encrypted=m.totp_secret_encrypted,
        totp_enabled=m.totp_enabled,
        role=m.role,
        is_active=m.is_active,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


def _identity_to_entity(m: UserIdentityModel) -> UserIdentity:
    return UserIdentity(
        id=m.id,
        user_id=m.user_id,
        provider=m.provider,
        provider_user_id=m.provider_user_id,
        password_hash=m.password_hash,
        access_token=m.access_token,
        refresh_token=m.refresh_token,
        created_at=m.created_at,
        last_used_at=m.last_used_at,
    )


def _app_to_entity(m: TenantApplicationModel) -> TenantApplication:
    return TenantApplication(
        id=m.id,
        owner_id=m.owner_id,
        name=m.name,
        liveness_threshold=m.liveness_threshold,
        similarity_threshold=m.similarity_threshold,
        allowed_ips=m.allowed_ips or [],
        allowed_origins=m.allowed_origins or [],
        status=m.status,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


def _apikey_to_entity(m: ApiKeyModel) -> ApiKey:
    return ApiKey(
        id=m.id,
        app_id=m.app_id,
        key_prefix=m.key_prefix,
        key_hash=m.key_hash,
        label=m.label,
        key_type=m.key_type,
        status=m.status,
        last_used_at=m.last_used_at,
        expires_at=m.expires_at,
        created_at=m.created_at,
        revoked_at=m.revoked_at,
    )


def _face_to_entity(m: FaceProfileModel) -> FaceProfile:
    return FaceProfile(
        id=m.id,
        app_id=m.app_id,
        external_user_id=m.external_user_id,
        embedding_encrypted=m.embedding_encrypted,
        model_version=m.model_version,
        is_active=m.is_active,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


def _session_to_entity(m: AuthSessionModel) -> AuthSession:
    return AuthSession(
        id=m.id,
        app_id=m.app_id,
        session_type=m.session_type,
        status=m.status,
        lifecycle_state=m.lifecycle_state,
        failure_reason=m.failure_reason,
        expires_at=m.expires_at,
        idempotency_key=m.idempotency_key,
        sdk_version=m.sdk_version,
        client_secret_hash=m.client_secret_hash,
        return_url=m.return_url,
        cancel_url=m.cancel_url,
        locked_at=m.locked_at,
        exchange_code_hash=m.exchange_code_hash,
        exchange_code_expires_at=m.exchange_code_expires_at,
        exchanged_at=m.exchanged_at,
        external_user_id=m.external_user_id,
        liveness_class=m.liveness_class,
        liveness_confidence=m.liveness_confidence,
        similarity_score=m.similarity_score,
        inference_time_ms=m.inference_time_ms,
        client_metadata=m.client_metadata,
        created_at=m.created_at,
        completed_at=m.completed_at,
    )


def _refresh_token_to_entity(m: RefreshTokenModel) -> RefreshToken:
    return RefreshToken(
        id=m.id,
        user_id=m.user_id,
        token_hash=m.token_hash,
        is_revoked=m.is_revoked,
        expires_at=m.expires_at,
        created_at=m.created_at,
    )


# =============================================================================
# Repository Implementations
# =============================================================================


class SQLUserRepository(AbstractUserRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, user: User) -> User:
        model = UserModel(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            totp_secret_encrypted=user.totp_secret_encrypted,
            totp_enabled=user.totp_enabled,
            role=user.role,
            is_active=user.is_active,
        )
        self._session.add(model)
        await self._session.flush()
        return _user_to_entity(model)

    async def get_by_id(self, user_id: UUID) -> User | None:
        result = await self._session.get(UserModel, user_id)
        return _user_to_entity(result) if result else None

    async def get_by_email(self, email: str) -> User | None:
        stmt = select(UserModel).where(UserModel.email == email.lower())
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return _user_to_entity(model) if model else None

    async def update(self, user: User) -> User:
        stmt = (
            update(UserModel)
            .where(UserModel.id == user.id)
            .values(
                email=user.email,
                display_name=user.display_name,
                totp_secret_encrypted=user.totp_secret_encrypted,
                totp_enabled=user.totp_enabled,
                role=user.role,
                is_active=user.is_active,
                updated_at=datetime.datetime.now(datetime.timezone.utc),
            )
        )
        await self._session.execute(stmt)
        return user

    async def get_identity(self, provider: str, provider_user_id: str) -> UserIdentity | None:
        stmt = select(UserIdentityModel).where(
            and_(
                UserIdentityModel.provider == provider,
                UserIdentityModel.provider_user_id == provider_user_id
            )
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return _identity_to_entity(model) if model else None

    async def get_identities_by_user(self, user_id: UUID) -> list[UserIdentity]:
        stmt = select(UserIdentityModel).where(UserIdentityModel.user_id == user_id)
        result = await self._session.execute(stmt)
        return [_identity_to_entity(m) for m in result.scalars().all()]

    async def create_identity(self, identity: UserIdentity) -> UserIdentity:
        model = UserIdentityModel(
            id=identity.id,
            user_id=identity.user_id,
            provider=identity.provider,
            provider_user_id=identity.provider_user_id,
            password_hash=identity.password_hash,
            access_token=identity.access_token,
            refresh_token=identity.refresh_token,
        )
        self._session.add(model)
        await self._session.flush()
        return _identity_to_entity(model)

    async def update_identity(self, identity: UserIdentity) -> UserIdentity:
        stmt = (
            update(UserIdentityModel)
            .where(UserIdentityModel.id == identity.id)
            .values(
                password_hash=identity.password_hash,
                access_token=identity.access_token,
                refresh_token=identity.refresh_token,
                last_used_at=datetime.datetime.now(datetime.timezone.utc),
            )
        )
        await self._session.execute(stmt)
        return identity


class SQLTenantApplicationRepository(AbstractTenantApplicationRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, app: TenantApplication) -> TenantApplication:
        model = TenantApplicationModel(
            id=app.id,
            owner_id=app.owner_id,
            name=app.name,
            liveness_threshold=app.liveness_threshold,
            similarity_threshold=app.similarity_threshold,
            allowed_ips=app.allowed_ips,
            allowed_origins=app.allowed_origins,
            status=app.status,
        )
        self._session.add(model)
        await self._session.flush()
        return _app_to_entity(model)

    async def get_by_id(self, app_id: UUID) -> TenantApplication | None:
        result = await self._session.get(TenantApplicationModel, app_id)
        return _app_to_entity(result) if result else None

    async def list_by_owner(
        self, owner_id: UUID, *, offset: int = 0, limit: int = 50
    ) -> list[TenantApplication]:
        stmt = (
            select(TenantApplicationModel)
            .where(
                and_(
                    TenantApplicationModel.owner_id == owner_id,
                    TenantApplicationModel.status != "deleted",
                )
            )
            .offset(offset)
            .limit(limit)
            .order_by(TenantApplicationModel.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return [_app_to_entity(m) for m in result.scalars().all()]

    async def update(self, app: TenantApplication) -> TenantApplication:
        stmt = (
            update(TenantApplicationModel)
            .where(TenantApplicationModel.id == app.id)
            .values(
                name=app.name,
                liveness_threshold=app.liveness_threshold,
                similarity_threshold=app.similarity_threshold,
                allowed_ips=app.allowed_ips,
                allowed_origins=app.allowed_origins,
                status=app.status,
            )
        )
        await self._session.execute(stmt)
        return app

    async def soft_delete(self, app_id: UUID) -> None:
        stmt = (
            update(TenantApplicationModel)
            .where(TenantApplicationModel.id == app_id)
            .values(status="deleted")
        )
        await self._session.execute(stmt)


class SQLApiKeyRepository(AbstractApiKeyRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, api_key: ApiKey) -> ApiKey:
        model = ApiKeyModel(
            id=api_key.id,
            app_id=api_key.app_id,
            key_prefix=api_key.key_prefix,
            key_hash=api_key.key_hash,
            label=api_key.label,
            key_type=api_key.key_type,
            status=api_key.status,
            expires_at=api_key.expires_at,
        )
        self._session.add(model)
        await self._session.flush()
        return _apikey_to_entity(model)

    async def get_by_id(self, key_id: UUID) -> ApiKey | None:
        result = await self._session.get(ApiKeyModel, key_id)
        return _apikey_to_entity(result) if result else None

    async def get_by_prefix(self, prefix: str) -> ApiKey | None:
        stmt = select(ApiKeyModel).where(ApiKeyModel.key_prefix == prefix)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return _apikey_to_entity(model) if model else None

    async def list_by_app(self, app_id: UUID) -> list[ApiKey]:
        stmt = (
            select(ApiKeyModel)
            .where(ApiKeyModel.app_id == app_id)
            .order_by(ApiKeyModel.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return [_apikey_to_entity(m) for m in result.scalars().all()]

    async def revoke(self, key_id: UUID) -> None:
        stmt = (
            update(ApiKeyModel)
            .where(ApiKeyModel.id == key_id)
            .values(
                status="revoked",
                revoked_at=datetime.datetime.now(datetime.timezone.utc),
            )
        )
        await self._session.execute(stmt)

    async def delete(self, key_id: UUID) -> None:
        # Hard delete — row is removed. Intended for cleanup of keys that
        # were generated by mistake, never used, or already revoked and no
        # longer needed in the UI.
        from sqlalchemy import delete as sa_delete
        stmt = sa_delete(ApiKeyModel).where(ApiKeyModel.id == key_id)
        await self._session.execute(stmt)

    async def update_last_used(self, key_id: UUID) -> None:
        stmt = (
            update(ApiKeyModel)
            .where(ApiKeyModel.id == key_id)
            .values(last_used_at=datetime.datetime.now(datetime.timezone.utc))
        )
        await self._session.execute(stmt)


class SQLFaceProfileRepository(AbstractFaceProfileRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, profile: FaceProfile) -> FaceProfile:
        model = FaceProfileModel(
            id=profile.id,
            app_id=profile.app_id,
            external_user_id=profile.external_user_id,
            embedding_encrypted=profile.embedding_encrypted,
            model_version=profile.model_version,
            is_active=profile.is_active,
        )
        self._session.add(model)
        await self._session.flush()
        return _face_to_entity(model)

    async def get_by_external_user(
        self, app_id: UUID, external_user_id: str
    ) -> FaceProfile | None:
        stmt = select(FaceProfileModel).where(
            and_(
                FaceProfileModel.app_id == app_id,
                FaceProfileModel.external_user_id == external_user_id,
                FaceProfileModel.is_active.is_(True),
            )
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return _face_to_entity(model) if model else None

    async def exists(
        self, app_id: UUID, external_user_id: str
    ) -> bool:
        # Cheap existence probe backed by the unique index
        # ix_face_profiles_app_id_external_user_id. Does not deserialize the
        # row. Intended as the single-query source of truth for frontend
        # "should I register or authenticate?" decisions.
        stmt = select(FaceProfileModel.id).where(
            and_(
                FaceProfileModel.app_id == app_id,
                FaceProfileModel.external_user_id == external_user_id,
                FaceProfileModel.is_active.is_(True),
            )
        ).limit(1)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def update(self, profile: FaceProfile) -> FaceProfile:
        stmt = (
            update(FaceProfileModel)
            .where(FaceProfileModel.id == profile.id)
            .values(
                embedding_encrypted=profile.embedding_encrypted,
                model_version=profile.model_version,
                is_active=profile.is_active,
            )
        )
        await self._session.execute(stmt)
        return profile

    async def delete(self, app_id: UUID, external_user_id: str) -> None:
        stmt = delete(FaceProfileModel).where(
            and_(
                FaceProfileModel.app_id == app_id,
                FaceProfileModel.external_user_id == external_user_id,
            )
        )
        await self._session.execute(stmt)

    async def list_by_app(
        self, app_id: UUID, *, offset: int = 0, limit: int = 50
    ) -> list[FaceProfile]:
        stmt = (
            select(FaceProfileModel)
            .where(FaceProfileModel.app_id == app_id)
            .order_by(FaceProfileModel.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [_face_to_entity(m) for m in result.scalars().all()]

    async def delete_all(self, app_id: UUID) -> int:
        stmt = delete(FaceProfileModel).where(FaceProfileModel.app_id == app_id)
        result = await self._session.execute(stmt)
        return result.rowcount


class SQLAuthSessionRepository(AbstractAuthSessionRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, session: AuthSession) -> AuthSession:
        model = AuthSessionModel(
            id=session.id,
            app_id=session.app_id,
            session_type=session.session_type,
            status=session.status,
            lifecycle_state=session.lifecycle_state,
            failure_reason=session.failure_reason,
            expires_at=session.expires_at,
            idempotency_key=session.idempotency_key,
            sdk_version=session.sdk_version,
            client_secret_hash=session.client_secret_hash,
            return_url=session.return_url,
            cancel_url=session.cancel_url,
            locked_at=session.locked_at,
            exchange_code_hash=session.exchange_code_hash,
            exchange_code_expires_at=session.exchange_code_expires_at,
            exchanged_at=session.exchanged_at,
            external_user_id=session.external_user_id,
            liveness_class=session.liveness_class,
            liveness_confidence=session.liveness_confidence,
            similarity_score=session.similarity_score,
            inference_time_ms=session.inference_time_ms,
            client_metadata=session.client_metadata,
            created_at=session.created_at,
            completed_at=session.completed_at,
        )
        self._session.add(model)
        await self._session.flush()
        return _session_to_entity(model)

    async def get_by_id(self, session_id: UUID) -> AuthSession | None:
        result = await self._session.get(AuthSessionModel, session_id)
        return _session_to_entity(result) if result else None

    async def get_by_idempotency_key(
        self, app_id: UUID, idempotency_key: str
    ) -> AuthSession | None:
        stmt = select(AuthSessionModel).where(
            and_(
                AuthSessionModel.app_id == app_id,
                AuthSessionModel.idempotency_key == idempotency_key,
            )
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return _session_to_entity(model) if model else None

    async def get_by_exchange_code_hash(
        self, exchange_code_hash: str
    ) -> AuthSession | None:
        stmt = select(AuthSessionModel).where(
            AuthSessionModel.exchange_code_hash == exchange_code_hash
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return _session_to_entity(model) if model else None

    async def update(self, session: AuthSession) -> AuthSession:
        stmt = (
            update(AuthSessionModel)
            .where(AuthSessionModel.id == session.id)
            .values(
                status=session.status,
                lifecycle_state=session.lifecycle_state,
                failure_reason=session.failure_reason,
                expires_at=session.expires_at,
                idempotency_key=session.idempotency_key,
                sdk_version=session.sdk_version,
                client_secret_hash=session.client_secret_hash,
                return_url=session.return_url,
                cancel_url=session.cancel_url,
                locked_at=session.locked_at,
                exchange_code_hash=session.exchange_code_hash,
                exchange_code_expires_at=session.exchange_code_expires_at,
                exchanged_at=session.exchanged_at,
                liveness_class=session.liveness_class,
                liveness_confidence=session.liveness_confidence,
                similarity_score=session.similarity_score,
                inference_time_ms=session.inference_time_ms,
                client_metadata=session.client_metadata,
                completed_at=session.completed_at,
            )
        )
        await self._session.execute(stmt)
        return session

    async def list_by_app(
        self,
        app_id: UUID,
        *,
        offset: int = 0,
        limit: int = 50,
        status: str | None = None,
    ) -> list[AuthSession]:
        stmt = select(AuthSessionModel).where(AuthSessionModel.app_id == app_id)
        if status:
            stmt = stmt.where(AuthSessionModel.status == status)
        stmt = stmt.offset(offset).limit(limit).order_by(
            AuthSessionModel.created_at.desc()
        )
        result = await self._session.execute(stmt)
        return [_session_to_entity(m) for m in result.scalars().all()]


class SQLRefreshTokenRepository(AbstractRefreshTokenRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, token: RefreshToken) -> RefreshToken:
        model = RefreshTokenModel(
            id=token.id,
            user_id=token.user_id,
            token_hash=token.token_hash,
            is_revoked=token.is_revoked,
            expires_at=token.expires_at,
        )
        self._session.add(model)
        await self._session.flush()
        return _refresh_token_to_entity(model)

    async def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        stmt = select(RefreshTokenModel).where(
            RefreshTokenModel.token_hash == token_hash
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return _refresh_token_to_entity(model) if model else None

    async def revoke(self, token_id: UUID) -> None:
        stmt = (
            update(RefreshTokenModel)
            .where(RefreshTokenModel.id == token_id)
            .values(is_revoked=True)
        )
        await self._session.execute(stmt)

    async def revoke_all_for_user(self, user_id: UUID) -> None:
        stmt = (
            update(RefreshTokenModel)
            .where(
                and_(
                    RefreshTokenModel.user_id == user_id,
                    RefreshTokenModel.is_revoked.is_(False),
                )
            )
            .values(is_revoked=True)
        )
        await self._session.execute(stmt)


class SQLAuditLogRepository(AbstractAuditLogRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

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
    ) -> None:
        import uuid

        model = AuditLogModel(
            id=uuid.uuid4(),
            event_type=event_type,
            app_id=app_id,
            user_id=user_id,
            api_key_id=api_key_id,
            resource_type=resource_type,
            resource_id=resource_id,
            metadata_=metadata,
            ip_address=ip_address,
        )
        self._session.add(model)
        await self._session.flush()


class SQLWebhookRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_endpoint(
        self,
        *,
        endpoint_id: UUID,
        app_id: UUID,
        url: str,
        secret_encrypted: str,
        event_types: list[str],
    ) -> dict[str, Any]:
        model = WebhookEndpointModel(
            id=endpoint_id,
            app_id=app_id,
            url=url,
            secret_encrypted=secret_encrypted,
            event_types=event_types,
            status="active",
        )
        self._session.add(model)
        await self._session.flush()
        return self._endpoint_to_dict(model, include_secret=True)

    async def list_endpoints_by_app(self, app_id: UUID) -> list[dict[str, Any]]:
        stmt = (
            select(WebhookEndpointModel)
            .where(WebhookEndpointModel.app_id == app_id)
            .order_by(WebhookEndpointModel.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return [self._endpoint_to_dict(model) for model in result.scalars().all()]

    async def list_active_endpoints_for_event(
        self, app_id: UUID, event_type: str
    ) -> list[WebhookEndpointModel]:
        stmt = select(WebhookEndpointModel).where(
            and_(
                WebhookEndpointModel.app_id == app_id,
                WebhookEndpointModel.status == "active",
            )
        )
        result = await self._session.execute(stmt)
        endpoints = result.scalars().all()
        return [
            endpoint
            for endpoint in endpoints
            if not endpoint.event_types or event_type in endpoint.event_types
        ]

    async def disable_endpoint(self, endpoint_id: UUID, app_id: UUID) -> bool:
        stmt = (
            update(WebhookEndpointModel)
            .where(
                and_(
                    WebhookEndpointModel.id == endpoint_id,
                    WebhookEndpointModel.app_id == app_id,
                )
            )
            .values(
                status="disabled",
                disabled_at=datetime.datetime.now(datetime.timezone.utc),
            )
        )
        result = await self._session.execute(stmt)
        return bool(result.rowcount)

    async def record_event(
        self,
        *,
        event_id: str,
        app_id: UUID,
        event_type: str,
        payload: dict[str, Any],
    ) -> tuple[dict[str, Any], bool]:
        existing = await self._session.get(SpectreEventModel, event_id)
        if existing is not None:
            return self._event_to_dict(existing), False

        model = SpectreEventModel(
            id=event_id,
            app_id=app_id,
            event_type=event_type,
            payload=payload,
        )
        self._session.add(model)
        await self._session.flush()
        return self._event_to_dict(model), True

    async def create_delivery(
        self,
        *,
        delivery_id: UUID,
        event_id: str,
        endpoint_id: UUID,
        signature_header: str,
    ) -> dict[str, Any]:
        model = WebhookDeliveryModel(
            id=delivery_id,
            event_id=event_id,
            endpoint_id=endpoint_id,
            status="pending",
            signature_header=signature_header,
        )
        self._session.add(model)
        await self._session.flush()
        return {
            "id": str(model.id),
            "event_id": model.event_id,
            "endpoint_id": str(model.endpoint_id),
            "status": model.status,
            "signature_header": model.signature_header,
            "created_at": model.created_at.isoformat() if model.created_at else None,
        }

    @staticmethod
    def _endpoint_to_dict(
        model: WebhookEndpointModel, *, include_secret: bool = False
    ) -> dict[str, Any]:
        data = {
            "id": str(model.id),
            "app_id": str(model.app_id),
            "url": model.url,
            "event_types": model.event_types or [],
            "status": model.status,
            "created_at": model.created_at.isoformat() if model.created_at else None,
            "disabled_at": model.disabled_at.isoformat() if model.disabled_at else None,
        }
        if include_secret:
            data["secret_encrypted"] = model.secret_encrypted
        return data

    @staticmethod
    def _event_to_dict(model: SpectreEventModel) -> dict[str, Any]:
        return {
            "id": model.id,
            "app_id": str(model.app_id),
            "type": model.event_type,
            "payload": model.payload,
            "created_at": model.created_at.isoformat() if model.created_at else None,
        }


class SQLConfigRepository(AbstractConfigRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_all(self) -> list[dict[str, Any]]:
        result = await self._session.execute(
            select(SystemConfigModel).order_by(SystemConfigModel.category, SystemConfigModel.key)
        )
        return [self._to_dict(m) for m in result.scalars().all()]

    async def get_by_category(self, category: str) -> list[dict[str, Any]]:
        result = await self._session.execute(
            select(SystemConfigModel).where(SystemConfigModel.category == category)
        )
        return [self._to_dict(m) for m in result.scalars().all()]

    async def get_by_key(self, key: str) -> dict[str, Any] | None:
        result = await self._session.execute(
            select(SystemConfigModel).where(SystemConfigModel.key == key)
        )
        model = result.scalar_one_or_none()
        return self._to_dict(model) if model else None

    async def update_value(self, key: str, value: str, updated_by: UUID | None = None) -> dict[str, Any] | None:
        stmt = (
            update(SystemConfigModel)
            .where(SystemConfigModel.key == key)
            .values(value=value, updated_by=updated_by)
            .returning(SystemConfigModel)
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_dict(model) if model else None

    @staticmethod
    def _to_dict(m: SystemConfigModel) -> dict[str, Any]:
        return {
            "key": m.key,
            "value": m.value,
            "category": m.category,
            "data_type": m.data_type,
            "description": m.description,
            "updated_by": str(m.updated_by) if m.updated_by else None,
            "updated_at": m.updated_at.isoformat() if m.updated_at else None,
        }
