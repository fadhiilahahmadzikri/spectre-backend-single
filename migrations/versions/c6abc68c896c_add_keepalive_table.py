"""add_keepalive_table

Revision ID: c6abc68c896c
Revises: 6c915d21ab82
Create Date: 2026-05-10 19:15:26.251567

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c6abc68c896c'
down_revision: Union[str, None] = '6c915d21ab82'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('keepalive_ping',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('pinged_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('source', sa.String(length=50), server_default='github-actions', nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_keepalive_ping'))
    )


def downgrade() -> None:
    op.drop_table('keepalive_ping')
