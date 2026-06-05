"""Seed registry — idempotency tracking for database seeders.

Stores which seeders have run so re-executing is always safe.
Uses a dedicated ``seed_registry`` table (auto-created on first use).
"""

from __future__ import annotations

import hashlib
import inspect
from datetime import datetime, timezone

from sqlalchemy import DateTime, String, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class SeedBase(DeclarativeBase):
    """Separate declarative base for seed infrastructure (not app models)."""

    pass


class SeedRecord(SeedBase):
    """Tracks individual seeder execution state."""

    __tablename__ = "seed_registry"

    name: Mapped[str] = mapped_column(String(255), primary_key=True)
    checksum: Mapped[str] = mapped_column(String(64))
    seeded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SeedRegistry:
    """Registry for checking and recording seeder runs."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _checksum(seeder_class: type) -> str:
        source = inspect.getsource(seeder_class)
        return hashlib.sha256(source.encode()).hexdigest()[:16]

    async def ensure_table(self, engine: AsyncEngine) -> None:
        """Create the seed_registry table if it doesn't exist."""
        async with engine.begin() as conn:
            await conn.run_sync(SeedBase.metadata.create_all)

    async def has_run(self, name: str) -> bool:
        result = await self._session.execute(
            select(SeedRecord).where(SeedRecord.name == name)
        )
        return result.scalar_one_or_none() is not None

    async def mark_done(self, name: str, seeder_class: type) -> None:
        record = SeedRecord(
            name=name,
            checksum=self._checksum(seeder_class),
            seeded_at=datetime.now(timezone.utc),
        )
        self._session.add(record)
        await self._session.flush()

    async def clear(self, name: str) -> None:
        result = await self._session.execute(
            select(SeedRecord).where(SeedRecord.name == name)
        )
        record = result.scalar_one_or_none()
        if record:
            await self._session.delete(record)
            await self._session.flush()
