"""Add share_token column to scans table

Revision ID: a1b2c3d4e5f6
Revises: e3b2e596d66e
Create Date: 2026-06-30
"""
from alembic import op
import sqlalchemy as sa

revision = 'a1b2c3d4e5f6'
down_revision = 'e3b2e596d66e'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add share_token column — nullable first so existing rows don't fail
    op.add_column('scans', sa.Column('share_token', sa.String(64), nullable=True))
    
    # Backfill existing rows with unique share tokens
    op.execute("""
        UPDATE scans 
        SET share_token = encode(gen_random_bytes(32), 'hex')
        WHERE share_token IS NULL
    """)
    
    # Now make it non-nullable and add unique constraint
    op.alter_column('scans', 'share_token', nullable=False)
    op.create_unique_constraint('uq_scans_share_token', 'scans', ['share_token'])
    op.create_index('ix_scans_share_token', 'scans', ['share_token'])


def downgrade() -> None:
    op.drop_index('ix_scans_share_token', table_name='scans')
    op.drop_constraint('uq_scans_share_token', 'scans', type_='unique')
    op.drop_column('scans', 'share_token')
