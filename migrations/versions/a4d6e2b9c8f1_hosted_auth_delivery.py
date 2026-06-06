"""hosted auth delivery schema

Revision ID: a4d6e2b9c8f1
Revises: 9f3b2c1d4e5f
Create Date: 2026-06-06 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import context, op
import sqlalchemy as sa


revision: str = "a4d6e2b9c8f1"
down_revision: str | None = "9f3b2c1d4e5f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_table(table_name: str) -> bool:
    if context.is_offline_mode():
        return False
    inspector = sa.inspect(op.get_bind())
    return table_name in inspector.get_table_names()


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
) -> None:
    if not _has_index(table_name, index_name):
        op.create_index(index_name, table_name, columns, unique=unique)


def upgrade() -> None:
    _add_column_if_missing(
        "tenant_applications",
        sa.Column("allowed_origins", sa.JSON(), nullable=True),
    )

    _add_column_if_missing(
        "api_keys",
        sa.Column(
            "key_type",
            sa.String(length=20),
            nullable=False,
            server_default="legacy",
        ),
    )
    _create_index_if_missing(
        "ix_api_keys_app_key_type_status",
        "api_keys",
        ["app_id", "key_type", "status"],
    )

    for column in (
        sa.Column("client_secret_hash", sa.Text(), nullable=True),
        sa.Column("return_url", sa.Text(), nullable=True),
        sa.Column("cancel_url", sa.Text(), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("exchange_code_hash", sa.Text(), nullable=True),
        sa.Column("exchange_code_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("exchanged_at", sa.DateTime(timezone=True), nullable=True),
    ):
        _add_column_if_missing("auth_sessions", column)

    _create_index_if_missing(
        "ix_auth_sessions_exchange_code",
        "auth_sessions",
        ["exchange_code_hash"],
    )

    if not _has_table("webhook_endpoints"):
        op.create_table(
            "webhook_endpoints",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("app_id", sa.UUID(), nullable=False),
            sa.Column("url", sa.Text(), nullable=False),
            sa.Column("secret_encrypted", sa.Text(), nullable=False),
            sa.Column("event_types", sa.JSON(), nullable=True),
            sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["app_id"], ["tenant_applications.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index_if_missing(
        "ix_webhook_endpoints_app_status",
        "webhook_endpoints",
        ["app_id", "status"],
    )

    if not _has_table("spectre_events"):
        op.create_table(
            "spectre_events",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("app_id", sa.UUID(), nullable=False),
            sa.Column("event_type", sa.String(length=80), nullable=False),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["app_id"], ["tenant_applications.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index_if_missing(
        "ix_spectre_events_app_created_at",
        "spectre_events",
        ["app_id", "created_at"],
    )
    _create_index_if_missing("ix_spectre_events_type", "spectre_events", ["event_type"])

    if not _has_table("webhook_deliveries"):
        op.create_table(
            "webhook_deliveries",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("event_id", sa.String(length=64), nullable=False),
            sa.Column("endpoint_id", sa.UUID(), nullable=False),
            sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
            sa.Column("signature_header", sa.Text(), nullable=False),
            sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
            sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("response_status", sa.Integer(), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["event_id"], ["spectre_events.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["endpoint_id"], ["webhook_endpoints.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("event_id", "endpoint_id", name="uq_webhook_delivery_event_endpoint"),
        )
    _create_index_if_missing(
        "ix_webhook_deliveries_event",
        "webhook_deliveries",
        ["event_id"],
    )
    _create_index_if_missing(
        "ix_webhook_deliveries_endpoint_status",
        "webhook_deliveries",
        ["endpoint_id", "status"],
    )


def downgrade() -> None:
    # Forward-only stabilization migration. Do not drop columns/tables in rollback.
    pass
