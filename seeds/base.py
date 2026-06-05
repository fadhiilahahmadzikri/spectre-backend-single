"""Base seeder class — all seeders inherit from this.

Enforces interface, handles idempotency, and provides session access.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from sqlalchemy.ext.asyncio import AsyncSession

from seeds.registry import SeedRegistry


class BaseSeeder(ABC):
    """Abstract base for all database seeders."""

    name: str
    priority: int = 50
    idempotent: bool = True

    def __init__(self, session: AsyncSession, registry: SeedRegistry) -> None:
        self._session = session
        self._registry = registry

    @abstractmethod
    async def run(self) -> None:
        """Execute the seeding logic. Subclasses implement this."""
        ...

    async def execute(self, force: bool = False) -> str:
        """Run the seeder with idempotency check.

        Returns:
            'seeded' if data was inserted, 'skipped' if already run.
        """
        if self.idempotent and not force:
            if await self._registry.has_run(self.name):
                return "skipped"

        await self.run()
        await self._session.flush()

        if self.idempotent:
            await self._registry.mark_done(self.name, self.__class__)

        return "seeded"
