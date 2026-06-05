"""remove_email_verification_system

Revision ID: 2bbadc2311f5
Revises: e3f7bd8c1205
Create Date: 2026-05-12 18:09:20.217405

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2bbadc2311f5'
down_revision: Union[str, None] = 'e3f7bd8c1205'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop email_verifications table
    op.drop_table('email_verifications')
    
    # Remove is_verified column from users table
    op.drop_column('users', 'is_verified')


def downgrade() -> None:
    # Add is_verified column back to users table
    op.add_column('users', sa.Column('is_verified', sa.BOOLEAN(), autoincrement=False, nullable=True))
    # Default existing users to verified
    op.execute("UPDATE users SET is_verified = TRUE")
    # Make it non-nullable
    op.alter_column('users', 'is_verified', nullable=False)
    
    # Re-create email_verifications table
    op.create_table('email_verifications',
        sa.Column('id', sa.UUID(), autoincrement=False, nullable=False),
        sa.Column('user_id', sa.UUID(), autoincrement=False, nullable=False),
        sa.Column('otp_hash', sa.VARCHAR(length=255), autoincrement=False, nullable=False),
        sa.Column('is_used', sa.BOOLEAN(), autoincrement=False, nullable=False),
        sa.Column('expires_at', sa.TIMESTAMP(timezone=True), autoincrement=False, nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_email_verifications_user_id_users', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name='pk_email_verifications')
    )
