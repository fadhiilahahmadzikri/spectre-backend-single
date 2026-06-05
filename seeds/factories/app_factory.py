"""Factory seeder — generates tenant applications for faker users.

Priority 40: Depends on factory.users (priority 30).
Creates applications owned by the faker-generated users.
"""

from __future__ import annotations

import uuid

from faker import Faker
from sqlalchemy import select

from seeds.base import BaseSeeder
from spectre.config import get_settings
from spectre.infrastructure.database.models.tables import (
    ApiKeyModel,
    TenantApplicationModel,
    UserModel,
)
from spectre.infrastructure.security.api_key_generator import ApiKeyGenerator

_faker = Faker()


class AppSeeder(BaseSeeder):
    """Seed tenant applications for faker users."""

    name = "factory.apps"
    priority = 40
    COUNT = 5

    async def run(self) -> None:
        # Get all non-admin user IDs
        result = await self._session.execute(
            select(UserModel.id).where(UserModel.email != "admin@spectre.dev")
        )
        user_ids = result.scalars().all()

        if not user_ids:
            raise RuntimeError("UserSeeder must run before AppSeeder")

        keygen = ApiKeyGenerator(get_settings())

        for i in range(min(self.COUNT, len(user_ids))):
            app_id = uuid.uuid4()
            app = TenantApplicationModel(
                id=app_id,
                owner_id=user_ids[i],
                name=f"{_faker.company()} FaceAuth",
                liveness_threshold=0.5,
                similarity_threshold=0.40,
                status="active",
            )
            self._session.add(app)
            await self._session.flush()

            # Create one API key per app
            pair = keygen.generate()
            api_key = ApiKeyModel(
                id=uuid.uuid4(),
                app_id=app_id,
                key_prefix=pair.prefix,
                key_hash=pair.key_hash,
                label="Auto-generated",
                status="active",
            )
            self._session.add(api_key)
