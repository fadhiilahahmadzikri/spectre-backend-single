"""Factory seeder — generates bulk faker-based user accounts.

Priority 30: Depends on nothing (users have no FKs).
Creates randomized user accounts for load testing and development.
"""

from __future__ import annotations

import uuid

from faker import Faker

from seeds.base import BaseSeeder
from spectre.config import get_settings
from spectre.infrastructure.database.models.tables import UserModel
from spectre.infrastructure.security.password_handler import PasswordHandler

_faker = Faker(locale="id_ID")


class UserSeeder(BaseSeeder):
    """Seed bulk randomized user accounts."""

    name = "factory.users"
    priority = 30
    COUNT = 10

    async def run(self) -> None:
        pw = PasswordHandler(get_settings())
        default_hash = pw.hash("TestUser@123")

        for _ in range(self.COUNT):
            user = UserModel(
                id=uuid.uuid4(),
                email=f"{uuid.uuid4().hex[:8]}@{_faker.domain_name()}",
                password_hash=default_hash,
                display_name=_faker.name(),
                auth_provider="local",
                is_active=_faker.boolean(chance_of_getting_true=90),
            )
            self._session.add(user)
