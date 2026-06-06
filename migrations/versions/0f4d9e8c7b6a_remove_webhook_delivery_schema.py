"""remove webhook delivery schema

Revision ID: 0f4d9e8c7b6a
Revises: 9f3b2c1d4e5f
Create Date: 2026-06-06 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import context, op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision: str = "0f4d9e8c7b6a"
down_revision: str | None = "9f3b2c1d4e5f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


REMOVED_CONFIG_KEYS = (
    "webhook_timeout_seconds",
    "webhook_max_retries",
    "webhook_retry_backoff_base",
)


def _has_table(table_name: str) -> bool:
    if context.is_offline_mode():
        return True
    inspector = sa.inspect(op.get_bind())
    return table_name in inspector.get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    if context.is_offline_mode():
        return True
    inspector = sa.inspect(op.get_bind())
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("DELETE FROM system_config WHERE key IN :keys").bindparams(
            sa.bindparam("keys", expanding=True)
        ),
        {"keys": REMOVED_CONFIG_KEYS},
    )

    if _has_table("webhook_deliveries"):
        op.drop_table("webhook_deliveries")

    if _has_column("tenant_applications", "webhook_secret_encrypted"):
        op.drop_column("tenant_applications", "webhook_secret_encrypted")
    if _has_column("tenant_applications", "webhook_url"):
        op.drop_column("tenant_applications", "webhook_url")


def downgrade() -> None:
    if not _has_column("tenant_applications", "webhook_url"):
        op.add_column(
            "tenant_applications",
            sa.Column("webhook_url", sa.Text(), nullable=True),
        )
    if not _has_column("tenant_applications", "webhook_secret_encrypted"):
        op.add_column(
            "tenant_applications",
            sa.Column("webhook_secret_encrypted", sa.Text(), nullable=True),
        )

    if not _has_table("webhook_deliveries"):
        op.create_table(
            "webhook_deliveries",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "session_id",
                UUID(as_uuid=True),
                sa.ForeignKey("auth_sessions.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "app_id",
                UUID(as_uuid=True),
                sa.ForeignKey("tenant_applications.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="PENDING"),
            sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="4"),
            sa.Column("last_status_code", sa.Integer(), nullable=True),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column("payload_hash", sa.String(length=64), nullable=True),
            sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )
        op.create_index(
            "ix_webhook_deliveries_app_id_created_at",
            "webhook_deliveries",
            ["app_id", "created_at"],
        )
        op.create_index(
            "ix_webhook_deliveries_status_next_retry",
            "webhook_deliveries",
            ["status", "next_retry_at"],
        )
