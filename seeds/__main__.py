"""Spectre database seeder CLI.

Usage:
    python -m seeds list                  # list all registered seeders
    python -m seeds all                   # run all seeders (idempotent)
    python -m seeds all --force           # force re-run everything
    python -m seeds run static.admin_user # run a single seeder
    python -m seeds reset --yes           # clear registry

Configuration is read from environment variables (via spectre.config.Settings),
ensuring a single source of truth — no hardcoded DB URLs.
"""

from __future__ import annotations

import asyncio

import typer
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from seeds.runner import SeedRunner
from seeds.registry import SeedRegistry

from seeds.static.admin_user import AdminUserSeeder
from seeds.static.default_app import DefaultAppSeeder

# ---------------------------------------------------------------------------
# Seeder registry — ordered by priority (FK-safe)
# ---------------------------------------------------------------------------

ALL_SEEDERS = [
    AdminUserSeeder,    # 10 — admin user (no deps)
    DefaultAppSeeder,   # 20 — dev app + API key (→ admin user)
]

# Conditionally load Faker-based seeders (Dev only)
try:
    from seeds.factories.user_factory import UserSeeder
    from seeds.factories.app_factory import AppSeeder
    ALL_SEEDERS.extend([
        UserSeeder,     # 30 — faker users (no deps)
        AppSeeder,      # 40 — faker apps (→ faker users)
    ])
except ImportError:
    pass  # Production environment (no dev dependencies)

SEEDER_MAP = {s.name: s for s in ALL_SEEDERS}

cli = typer.Typer(help="Spectre database seeder CLI")


def _get_database_url() -> str:
    """Read DATABASE_URL from spectre.config — single source of truth."""
    from spectre.config import get_settings
    return get_settings().database_url


@cli.command("all")
def seed_all(
    force: bool = typer.Option(False, "--force", "-f", help="Re-run already seeded entries"),
) -> None:
    """Run all seeders in priority order."""

    async def _run() -> None:
        engine = create_async_engine(_get_database_url(), echo=False)
        async with AsyncSession(engine, expire_on_commit=False) as session:
            registry = SeedRegistry(session)
            await registry.ensure_table(engine)
            runner = SeedRunner(session)
            typer.echo(f"\n[*] Running {len(ALL_SEEDERS)} seeder(s)...\n")
            results = await runner.run_all(ALL_SEEDERS, force=force)
            seeded = sum(1 for v in results.values() if v == "seeded")
            skipped = sum(1 for v in results.values() if v == "skipped")
            typer.echo(f"\n[OK] Done -- {seeded} seeded, {skipped} skipped\n")
        await engine.dispose()

    asyncio.run(_run())


@cli.command("run")
def seed_one(
    name: str = typer.Argument(help="Seeder name, e.g. static.admin_user"),
    force: bool = typer.Option(False, "--force", "-f"),
) -> None:
    """Run a single seeder by name."""

    async def _run() -> None:
        if name not in SEEDER_MAP:
            typer.echo(f"❌ Unknown seeder: {name}")
            typer.echo(f"Available: {', '.join(SEEDER_MAP.keys())}")
            raise typer.Exit(1)
        engine = create_async_engine(_get_database_url(), echo=False)
        async with AsyncSession(engine, expire_on_commit=False) as session:
            registry = SeedRegistry(session)
            await registry.ensure_table(engine)
            runner = SeedRunner(session)
            await runner.run_one(SEEDER_MAP[name], force=force)
        await engine.dispose()

    asyncio.run(_run())


@cli.command("reset")
def reset_all(
    confirm: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Clear the seed registry so seeders can re-run."""
    if not confirm:
        typer.confirm(
            "This will clear the seed registry. Seeders can be re-run. Continue?",
            abort=True,
        )

    async def _run() -> None:
        engine = create_async_engine(_get_database_url(), echo=False)
        async with AsyncSession(engine, expire_on_commit=False) as session:
            registry = SeedRegistry(session)
            await registry.ensure_table(engine)
            runner = SeedRunner(session)
            await runner.reset(ALL_SEEDERS)
        await engine.dispose()
        typer.echo("[OK] Seed registry cleared. Run `python -m seeds all` to re-seed.")

    asyncio.run(_run())


@cli.command("list")
def list_seeders() -> None:
    """Show all registered seeders with priority and mode."""
    typer.echo("\nRegistered Seeders:\n")
    for s in sorted(ALL_SEEDERS, key=lambda x: x.priority):
        mode = "idempotent" if s.idempotent else "always-run"
        typer.echo(f"  [{s.priority:>3}] {s.name:<40} ({mode})")
    typer.echo("")


if __name__ == "__main__":
    cli()
