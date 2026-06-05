"""Static seeder — creates a default tenant application for the admin user.

Priority 20: Depends on admin user (priority 10).
Creates a dev application with an API key so face endpoints can be tested.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from seeds.base import BaseSeeder
from spectre.config import get_settings
from spectre.infrastructure.database.models.tables import (
    ApiKeyModel,
    TenantApplicationModel,
    UserModel,
)
from spectre.infrastructure.security.api_key_generator import ApiKeyGenerator


class DefaultAppSeeder(BaseSeeder):
    """Seed a default tenant application + API key for the admin user."""

    name = "static.default_app"
    priority = 20

    APP_NAME = "Spectre Dev App"

    async def run(self) -> None:
        # Find admin user
        result = await self._session.execute(
            select(UserModel).where(UserModel.email == "admin@spectre.dev")
        )
        admin = result.scalar_one_or_none()
        if admin is None:
            raise RuntimeError("AdminUserSeeder must run first (priority 10)")

        # Check if app already exists
        existing = await self._session.execute(
            select(TenantApplicationModel).where(
                TenantApplicationModel.owner_id == admin.id,
                TenantApplicationModel.name == self.APP_NAME,
            )
        )
        if existing.scalar_one_or_none() is not None:
            return

        app_id = uuid.uuid4()

        # Create application
        app = TenantApplicationModel(
            id=app_id,
            owner_id=admin.id,
            name=self.APP_NAME,
            liveness_threshold=0.5,
            similarity_threshold=0.40,
            status="active",
        )
        self._session.add(app)
        await self._session.flush()

        # Generate API key
        keygen = ApiKeyGenerator(get_settings())
        static_key = get_settings().static_api_key
        
        if static_key:
            from spectre.domain.value_objects.api_key_pair import ApiKeyPair
            pair = ApiKeyPair(
                full_key=static_key,
                prefix=static_key[:12],
                key_hash=keygen._context.hash(static_key)
            )
        else:
            pair = keygen.generate()
        api_key = ApiKeyModel(
            id=uuid.uuid4(),
            app_id=app_id,
            key_prefix=pair.prefix,
            key_hash=pair.key_hash,
            label="Development Key",
            status="active",
        )
        self._session.add(api_key)

        print(f"    [APP] App ID: {app_id}")
        print(f"    [KEY] API Key: {pair.full_key}")
        print(f"          (Save this key -- it cannot be retrieved later)")
