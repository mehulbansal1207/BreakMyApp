"""Add dynamic_scan_status and dynamic_scan_detail columns to scans table

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-07-10
"""
from alembic import op
import sqlalchemy as sa

revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Dynamic scan status: "skipped" | "install_failed" | "start_failed" | "success" | null
    # Phase 3b — nullable columns only, no backfill required, no pgcrypto needed.
    op.add_column(
        'scans',
        sa.Column('dynamic_scan_status', sa.String(32), nullable=True)
    )
    op.add_column(
        'scans',
        sa.Column('dynamic_scan_detail', sa.Text(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('scans', 'dynamic_scan_detail')
    op.drop_column('scans', 'dynamic_scan_status')
