"""sync_supabase_schema

Revision ID: c2c2c2c2c2c2
Revises: f1f1f1f1f1f1
Create Date: 2026-06-07 02:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c2c2c2c2c2c2'
down_revision: Union[str, None] = 'f1f1f1f1f1f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Drop experimental tables if they exist
    op.execute("DROP TABLE IF EXISTS webhook_deliveries CASCADE;")
    op.execute("DROP TABLE IF EXISTS webhook_endpoints CASCADE;")
    op.execute("DROP TABLE IF EXISTS spectre_events CASCADE;")
    
    # 2. Re-create webhook_deliveries table matching the main branch schema
    op.create_table(
        'webhook_deliveries',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('session_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('app_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('status', sa.String(length=20), server_default='PENDING', nullable=False),
        sa.Column('attempt_count', sa.Integer(), default=0, nullable=False),
        sa.Column('max_attempts', sa.Integer(), default=4, nullable=False),
        sa.Column('last_status_code', sa.Integer(), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('payload_hash', sa.String(length=64), nullable=True),
        sa.Column('next_retry_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['app_id'], ['tenant_applications.id'], name='fk_webhook_deliveries_app_id_tenant_applications', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['session_id'], ['auth_sessions.id'], name='fk_webhook_deliveries_session_id_auth_sessions', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name='pk_webhook_deliveries')
    )
    
    # Create indexes for webhook_deliveries
    op.create_index('ix_webhook_deliveries_app_id_created_at', 'webhook_deliveries', ['app_id', 'created_at'])
    op.create_index('ix_webhook_deliveries_status_next_retry', 'webhook_deliveries', ['status', 'next_retry_at'])

    # 3. Clean up experimental columns on other tables
    op.execute("ALTER TABLE tenant_applications DROP COLUMN IF EXISTS allowed_origins;")
    op.execute("ALTER TABLE api_keys DROP COLUMN IF EXISTS key_type;")


def downgrade() -> None:
    pass
