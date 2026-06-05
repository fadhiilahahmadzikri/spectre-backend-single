"""fix_migration_fork_and_sync_with_supabase

Revision ID: e58ec07aec6a
Revises: 2bbadc2311f5
Create Date: 2026-05-12 19:04:07.704608

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e58ec07aec6a'
down_revision: Union[str, None] = '2bbadc2311f5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
