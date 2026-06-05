"""add benchmark config rows

Revision ID: e3f7bd8c1205
Revises: b8f3a1c92d01
Create Date: 2026-05-11 15:50:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "e3f7bd8c1205"
down_revision = "b8f3a1c92d01"
branch_labels = None
depends_on = None


ROWS = [
    (
        "benchmark_enabled",
        "false",
        "anti_spoofing",
        "bool",
        "Enable multi-model benchmark mode (runs all selected FAS models on the same image for side-by-side comparison)",
    ),
    (
        "benchmark_models",
        "[\"antispoofnet_v4\",\"ilhamcaesar_resnet50\"]",
        "anti_spoofing",
        "string",
        "JSON array of FAS model_ids participating in benchmark mode. Must all be loaded in the FAS registry.",
    ),
    (
        "detail_mode_default",
        "false",
        "anti_spoofing",
        "bool",
        "Default state of detail_mode toggle in the scan config drawer (client can still override per-session)",
    ),
]


def upgrade() -> None:
    conn = op.get_bind()
    for key, value, category, data_type, description in ROWS:
        conn.execute(
            sa.text(
                "INSERT INTO system_config (key, value, category, data_type, description) "
                "VALUES (:key, :value, :category, :data_type, :description) "
                "ON CONFLICT (key) DO NOTHING"
            ),
            {
                "key": key,
                "value": value,
                "category": category,
                "data_type": data_type,
                "description": description,
            },
        )


def downgrade() -> None:
    conn = op.get_bind()
    for key, *_ in ROWS:
        conn.execute(sa.text("DELETE FROM system_config WHERE key = :key"), {"key": key})
