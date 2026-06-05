"""Static seeder — creates the default admin user.

Priority 10: First seed — no FK dependencies.
Creates a verified admin user with a known password for development/testing.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from seeds.base import BaseSeeder
from spectre.config import get_settings
from spectre.infrastructure.database.models.tables import UserModel, UserIdentityModel
from spectre.infrastructure.security.password_handler import PasswordHandler


class AdminUserSeeder(BaseSeeder):
    """Seed the default admin user account."""

    name = "static.admin_user"
    priority = 10

    # Known admin credentials for development
    ADMIN_EMAIL = "admin@spectre.dev"
    ADMIN_PASSWORD = "Spectre@Admin123"
    ADMIN_DISPLAY_NAME = "Spectre Admin"
    
    # Primary Admin (User)
    PRIMARY_ADMIN = "zikri@students.amikom.ac.id"

    async def run(self) -> None:
        # Ensure default system admin
        existing_sys = await self._session.execute(
            select(UserModel).where(UserModel.email == self.ADMIN_EMAIL)
        )
        sys_user = existing_sys.scalar_one_or_none()
        if sys_user is None:
            sys_user = UserModel(
                id=uuid.uuid4(),
                email=self.ADMIN_EMAIL,
                display_name=self.ADMIN_DISPLAY_NAME,
                role="admin",
                is_active=True,
            )
            self._session.add(sys_user)
            
            pw = PasswordHandler(get_settings())
            sys_identity = UserIdentityModel(
                id=uuid.uuid4(),
                user_id=sys_user.id,
                provider="local",
                provider_user_id=self.ADMIN_EMAIL,
                password_hash=pw.hash(self.ADMIN_PASSWORD)
            )
            self._session.add(sys_identity)
        else:
            sys_user.role = "admin" # Recovery

        # Ensure Primary Admin exists with admin role
        existing_primary = await self._session.execute(
            select(UserModel).where(UserModel.email == self.PRIMARY_ADMIN)
        )
        primary = existing_primary.scalar_one_or_none()
        if primary:
            primary.role = "admin"
        else:
            # If not found, it will be created via OAuth with role 'user' 
            # and next boot will upgrade it to 'admin'.
            pass
