"""Google OAuth use cases — exchange profile for user account."""

from __future__ import annotations

import datetime
import uuid
from typing import Any

from spectre.core.logger import get_logger
from spectre.domain.entities.user import User, UserIdentity
from spectre.domain.ports.repositories import AbstractUserRepository

logger = get_logger(__name__)


class GoogleOAuthUseCase:
    """Handle Google OAuth profile to local user conversion using Identity Separation."""

    def __init__(self, user_repo: AbstractUserRepository) -> None:
        self._user_repo = user_repo

    async def execute(self, profile: dict[str, Any]) -> tuple[User, bool]:
        """Create or retrieve a user based on Google profile data.
        
        Returns:
            Tuple of (user, created_flag)
        """
        google_id = profile.get("sub")
        email = profile.get("email")
        display_name = profile.get("name")

        if not google_id or not email:
            from fastapi import HTTPException
            raise HTTPException(
                status_code=400, 
                detail={"error_code": "INVALID_OAUTH_PROFILE", "message": "Google profile missing required fields."}
            )

        provider = "google"
        
        # 1. Check if this identity is already known
        identity = await self._user_repo.get_identity(provider, google_id)
        if identity:
            # Known identity -> update last_used_at and return the associated user
            identity.last_used_at = datetime.datetime.now(datetime.timezone.utc)
            await self._user_repo.update_identity(identity)
            
            user = await self._user_repo.get_by_id(identity.user_id)
            if not user:
                 raise Exception("Integrity Error: User identity exists but user does not.")
            logger.info("google_oauth_login_existing_id", user_id=str(user.id), email=email)
            return user, False

        # 2. Identity is new. Check if the email is already registered in users
        user = await self._user_repo.get_by_email(email.lower())
        created = False
        
        if user:
            # Email exists -> Link the new Google identity to the existing user
            # We don't force re-verification if they are already verified
            logger.info("google_oauth_linked_account", user_id=str(user.id), email=email)
        else:
            # Completely new user -> Create user
            user = User(
                id=uuid.uuid4(),
                email=email.lower(),
                display_name=display_name,
                is_active=True,
            )
            user = await self._user_repo.create(user)
            created = True
            logger.info("google_oauth_new_user", user_id=str(user.id), email=email)

        # Create the new identity record (Google)
        new_identity = UserIdentity(
            id=uuid.uuid4(),
            user_id=user.id,
            provider=provider,
            provider_user_id=google_id,
        )
        await self._user_repo.create_identity(new_identity)
        
        return user, created
