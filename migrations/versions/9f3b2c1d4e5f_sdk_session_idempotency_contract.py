"""sdk session idempotency contract

Revision ID: 9f3b2c1d4e5f
Revises: e58ec07aec6a
Create Date: 2026-06-03 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import context, op
import sqlalchemy as sa


revision: str = "9f3b2c1d4e5f"
down_revision: str | None = "e58ec07aec6a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_column(table_name: str, column_name: str) -> bool:
    if context.is_offline_mode():
        return False
    inspector = sa.inspect(op.get_bind())
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def _has_index(table_name: str, index_name: str) -> bool:
    if context.is_offline_mode():
        return False
    inspector = sa.inspect(op.get_bind())
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    if not _has_column(table_name, column.name):
        op.add_column(table_name, column)


def _create_index_if_missing(
    index_name: str,
    table_name: str,
    columns: list[str],
    *,
    unique: bool = False,
    where: str | None = None,
) -> None:
    if _has_index(table_name, index_name):
        return
    kwargs = {}
    if where is not None:
        predicate = sa.text(where)
        kwargs["postgresql_where"] = predicate
        kwargs["sqlite_where"] = predicate
    op.create_index(index_name, table_name, columns, unique=unique, **kwargs)


def upgrade() -> None:
    _add_column_if_missing(
        "api_keys",
        sa.Column(
            "environment",
            sa.String(length=15),
            nullable=False,
            server_default="production",
        ),
    )
    _create_index_if_missing(
        "ix_api_keys_environment",
        "api_keys",
        ["environment", "status"],
    )

    _add_column_if_missing(
        "auth_sessions",
        sa.Column(
            "lifecycle_state",
            sa.String(length=20),
            nullable=False,
            server_default="PROCESSING",
        ),
    )
    _add_column_if_missing(
        "auth_sessions",
        sa.Column("failure_reason", sa.String(length=40), nullable=True),
    )
    _add_column_if_missing(
        "auth_sessions",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    _add_column_if_missing(
        "auth_sessions",
        sa.Column("idempotency_key", sa.String(length=64), nullable=True),
    )
    _add_column_if_missing(
        "auth_sessions",
        sa.Column("sdk_version", sa.String(length=20), nullable=True),
    )
    _create_index_if_missing(
        "ix_auth_sessions_app_idempotency",
        "auth_sessions",
        ["app_id", "idempotency_key"],
    )
    _create_index_if_missing(
        "ix_auth_sessions_lifecycle",
        "auth_sessions",
        ["lifecycle_state", "expires_at"],
    )
    _create_index_if_missing(
        "uq_auth_sessions_app_id_idempotency_key",
        "auth_sessions",
        ["app_id", "idempotency_key"],
        unique=True,
        where="idempotency_key IS NOT NULL",
    )


def downgrade() -> None:
    # Forward-only stabilization migration. Do not drop columns/indexes in rollback.
    pass
