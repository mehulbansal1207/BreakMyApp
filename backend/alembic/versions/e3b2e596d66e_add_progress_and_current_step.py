"""add progress and current_step columns to scans table

Revision ID: e3b2e596d66e
Revises: None
Create Date: 2026-06-29 11:25:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e3b2e596d66e'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add progress column to scans table: Integer, nullable, default 0
    op.add_column(
        'scans',
        sa.Column('progress', sa.Integer(), nullable=True, server_default='0')
    )
    # Add current_step column to scans table: String(255), nullable, default null
    op.add_column(
        'scans',
        sa.Column('current_step', sa.String(length=255), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('scans', 'current_step')
    op.drop_column('scans', 'progress')
