"""Seed runner — executes seeders in priority order with logging."""

from __future__ import annotations

import time
from typing import Type

from sqlalchemy.ext.asyncio import AsyncSession

from seeds.base import BaseSeeder
from seeds.registry import SeedRegistry


class SeedRunner:
    """Orchestrates seeder execution in FK-safe priority order."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._registry = SeedRegistry(session)

    @staticmethod
    def _sorted(seeders: list[Type[BaseSeeder]]) -> list[Type[BaseSeeder]]:
        return sorted(seeders, key=lambda s: s.priority)

    async def run_all(
        self, seeders: list[Type[BaseSeeder]], force: bool = False
    ) -> dict[str, str]:
        results: dict[str, str] = {}
        for SeederClass in self._sorted(seeders):
            seeder = SeederClass(self._session, self._registry)
            start = time.perf_counter()
            status = await seeder.execute(force=force)
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            results[SeederClass.name] = status
            symbol = "+" if status == "seeded" else "-"
            print(f"  {symbol} [{status:>7}] {SeederClass.name:<40} {duration_ms}ms")
        await self._session.commit()
        return results

    async def run_one(
        self, SeederClass: Type[BaseSeeder], force: bool = False
    ) -> str:
        seeder = SeederClass(self._session, self._registry)
        status = await seeder.execute(force=force)
        await self._session.commit()
        print(f"  + [{status}] {SeederClass.name}")
        return status

    async def reset(self, seeders: list[Type[BaseSeeder]]) -> None:
        for SeederClass in self._sorted(seeders):
            await self._registry.clear(SeederClass.name)
        await self._session.commit()
        print(f"  + Registry cleared for {len(seeders)} seeder(s)")
