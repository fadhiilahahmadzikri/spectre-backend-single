"""restore_webhook_columns

Revision ID: f1f1f1f1f1f1
Revises: 9f3b2c1d4e5f
Create Date: 2026-06-07 02:25:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1f1f1f1f1f1'
down_revision: Union[str, None] = '9f3b2c1d4e5f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Safely add columns if they don't exist
    op.execute("ALTER TABLE tenant_applications ADD COLUMN IF NOT EXISTS webhook_url TEXT;")
    op.execute("ALTER TABLE tenant_applications ADD COLUMN IF NOT EXISTS webhook_secret_encrypted TEXT;")


def downgrade() -> None:
    op.drop_column('tenant_applications', 'webhook_secret_encrypted')
    op.drop_column('tenant_applications', 'webhook_url')
